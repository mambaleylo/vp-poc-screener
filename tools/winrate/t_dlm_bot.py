"""v0.99.687 — ⚡ 4h wick limits in the bot: (1) features == the research (bot functions); (2) the model file; (3) the
virtual path re-makes backtest trades (scan at the 4h close -> the order at the same level, settle -> the fill and the
same R); (4) the real path on a fake exchange: a GTC limit placed, filled -> the stop trigger + the reduce-only take
limit, the take filled -> WIN; a second trade -> the time exit at the market; an order not filled -> cancelled; at most
DLM_MAX_POS positions. Run from the research folder (common.py, s20h4/ and the data)."""
import sys, json, time, bisect, numpy as np
from common import V
import os; os.environ["TFH"] = "4"
import s23_engine as E
ok = True
def bars(sym):
    T, O, H, L, C, Vv = E.load15(sym)
    return [{"time": int(t), "open": o, "high": h, "low": l, "close": c, "volume": v} for t, o, h, l, c, v in zip(T, O, H, L, C, Vv)]
CACHE = {}
def series(sym):
    if sym not in CACHE:
        b = bars(sym); CACHE[sym] = (b, [c["time"] for c in b])
    return CACHE[sym]
# (1) parity through the bot
B, BT = series("BTCUSDT")
rng = np.random.default_rng(5); tot = miss = 0; worst = np.zeros(33)
for sym in ("SOLUSDT", "DOGEUSDT"):
    b, bT = series(sym); z = np.load(f"s23_4h/{sym}.npz"); F2 = np.load(f"s24_4h/{sym}.npz")["F2"][:, [0, 1, 2, 5, 8]]
    F33 = np.full((len(z["t"]), 33), np.nan); F33[:, :28] = z["F"]; F33[z["fam"] == 2, 28:] = F2
    for k in rng.choice(np.flatnonzero((z["fam"] == 2) & (z["t"] >= 1704067200)), 30, replace=False):
        i = int(z["i"][k]); bj = bisect.bisect_right(BT, bT[i])
        cs = V.dlm_candidates4(b[max(0, i - 2999):i + 1], B[max(0, bj - 3000):bj], min_bars=0)
        m = [c for c in cs if c["side"] == int(z["side"][k])]
        tot += 1
        if not m: miss += 1; continue
        worst = np.maximum(worst, np.abs(np.array(m[0]["f"]) - F33[k].astype(np.float32).astype(float)))
print(f"(1) parity {tot} events, missed {miss}, max |diff| {worst.max():.2e}")
ok &= miss == 0 and worst.max() < 1e-3   # the research stores the features as float32
# (2) the model
m = V.dlm_model(); ok &= bool(m) and m["feats"] == V.DLM_FNAMES4 and m["ver"] == 2 and m["rule"]["bar_sec"] == 14400 and len(m["models"]) == 20 and m["side_cap"] == 20
print("(2) model", bool(m), m and m["thr"], m and m["rule"])
# (3) the virtual path on backtest trades (mocked candles from Binance 4h)
BL = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "/home/user/vp-poc-screener/vp_bt_trades.json"))["dlm"]
pool_ = [t for t in BL if t["t"] >= 1767225600 and not t.get("chk")]
picks = [t for t in pool_ if t["k"] == "take"][:4] + [t for t in pool_ if t["k"] == "stop"][:3] + [t for t in pool_ if t["k"] == "time"][:2]
def bname(gs):
    b = gs.replace("_USDT", "")
    for c in (b + "USDT", "1000" + b + "USDT"):
        try: series(c); return c, (1000.0 if c.startswith("1000") else 1.0)
        except Exception: pass
def scaled(lst, scl): return [dict(c, open=c["open"] / scl, high=c["high"] / scl, low=c["low"] / scl, close=c["close"] / scl) for c in lst]
def fake_closed(sym, tf, sec, n, now):
    src, scl = ("BTCUSDT", 1.0) if sym == "BTC_USDT" else bname(sym)
    return scaled([c for c in series(src)[0] if c["time"] + sec <= now][-n:], scl)
def fake_range(sym, tf, a, z_):
    src, scl = bname(sym)
    return scaled([c for c in series(src)[0] if a <= c["time"] <= z_], scl)
V._dlm_closed = fake_closed; V.get_candles_range = fake_range
V.dlm_save = lambda: None; V.heartbeat = lambda *a, **k: None; V.AUTOTRADE_ENABLED_DLM = False; V.DLM_BINANCE = False
hits = 0
for t in picks:
    V.RESEARCH_COINS_211 = V.RESEARCH_COINS_127 = (t["s"],); V._research_syms = lambda coins, n=300: list(coins)
    V._DLM.update({"orders": [], "trades": []})
    V.dlm_scan(t["t"])
    o = [x for x in V._DLM["orders"] if x["side"] == t["d"]]
    lv_ok = bool(o) and abs(o[0]["lv"] / t["lv"] - 1) < 1e-4   # the list keeps 10 decimals (SHIB ~1e-5) and o[0]["bs"] == 14400 and o[0]["until"] == t["t"] + 4 * 14400
    V.dlm_settle(t["t"] + 5 * 14400 + 30)
    V.dlm_settle(t["x"] + 14400)
    tr = [x for x in V._DLM["trades"] if x["side"] == t["d"]]
    r = tr[0]["r"] if tr else None
    same = r is not None and abs(r - t["r"]) < 0.01 and tr[0]["rv"] == V.DLM_MODEL_VER
    hits += lv_ok and same
    print(f"   {t['s']:12s} {t['d']:+d} order {'✓' if lv_ok else '✗'} · R bot {r} vs backtest {t['r']} ({t['k']}) {'✓' if same else '✗'}")
print(f"(3) {hits}/{len(picks)}"); ok &= hits >= len(picks) - 1
# (4) the real path on a fake exchange (Gate)
class X:
    def __init__(s): s.orders = {}; s.pos = {}; s.trig = {}; s.n = 0
    def req(s, method, path, body=None, query_string=None, **k):
        if method == "POST" and path == "/futures/usdt/orders":
            s.n += 1; oid = str(s.n); s.orders[oid] = dict(body, id=oid, left=abs(body["size"]), status="open", fill_price=None); return s.orders[oid]
        if method == "GET" and path == "/futures/usdt/orders":
            return [o for o in s.orders.values() if o["status"] == "open"]
        if method == "GET" and path.startswith("/futures/usdt/orders/"):
            return s.orders[path.rsplit("/", 1)[1]]
        if method == "DELETE" and path.startswith("/futures/usdt/orders/"):
            o = s.orders[path.rsplit("/", 1)[1]]; o["status"] = "finished"; return o
        raise RuntimeError(f"unexpected {method} {path}")
    def fill(s, oid):
        o = s.orders[oid]; o["left"] = 0; o["status"] = "finished"; o["fill_price"] = o["price"]
        s.pos[o["contract"]] = s.pos.get(o["contract"], 0) + int(o["size"])
X_ = X()
V.gate_signed_request = X_.req
V.get_open_positions = lambda: [{"contract": c, "size": v, "mark_price": "1"} for c, v in X_.pos.items() if v]
def trig(sym, d, px, rule, tick=None, price_type=0):
    X_.n += 1; X_.trig[str(X_.n)] = (sym, px); return {"id": X_.n}
V.place_close_trigger_order = trig
V.cancel_price_order = lambda oid: X_.trig.pop(str(oid), None)
V.get_open_price_orders = lambda: [{"id": k} for k in X_.trig]
V.get_contract_spec = lambda s: {"leverage_max": 50, "order_price_round": 0.0001, "order_size_min": 1, "quanto_multiplier": 1}
V.get_risk_limit_tiers_for_symbol = lambda s: None
V.get_futures_total_equity = lambda: 1000.0
V.get_futures_wallet_balance = lambda: 1000.0
risks = []
V.compute_risk_based_position = lambda *a, **k: (risks.append(k.get("risk_pct")), (50.0, 10, None))[1]
V.compute_contracts_from_margin = lambda *a, **k: (37, 1, 50.0, None)
V.set_leverage = lambda *a, **k: None
closed = []
V.close_position_for_mode = lambda mode, sym, d: (closed.append(sym), X_.pos.__setitem__(sym, 0), {"ok": True})[2]
V.notify_trade_result = lambda *a, **k: None
V.send_telegram = lambda *a, **k: None
V.AUTOTRADE_DRY_RUN = False; V.AUTOTRADE_ENABLED_DLM = True; V.MODULE_RISK_PCT["dlm"] = None
V._DLM.update({"orders": [], "trades": []})
now = time.time(); tb = int(now // 14400 * 14400)
mk = lambda sym, side, lv: {"id": f"dlm_{sym}_{side}_{tb}", "symbol": sym, "side": side, "lv": lv, "atr": 0.01, "score": 0.5, "t0": tb, "bs": 14400,
                            "until": tb + 4 * 14400, "px": lv + side * 0.02, "status": "OPEN", "real": None}
a, b_, c = mk("AAA_USDT", 1, 1.0), mk("BBB_USDT", -1, 2.0), mk("CCC_USDT", 1, 3.0)
V._DLM["orders"] += [a, b_, c]
for o in (a, b_, c): V.dlm_real_place(o)
placed = all((o.get("real") or {}).get("id") for o in (a, b_, c)) and risks and all(r == 4.0 for r in risks)
X_.fill(a["real"]["id"]); X_.fill(b_["real"]["id"])
V.dlm_real_tick()
ta = next(t for t in V._DLM["trades"] if t["symbol"] == "AAA_USDT"); tb_ = next(t for t in V._DLM["trades"] if t["symbol"] == "BBB_USDT")
exits_ok = bool(ta["real"].get("sl_id") and ta["real"].get("tp_id") and ta["real"].get("tp_kind") == "limit") and ta["hold"] == 32 and ta["until"] - ta["fbar"] == 32 * 14400
tp_order = X_.orders[ta["real"]["tp_id"]]
tp_ok = tp_order.get("reduce_only") and tp_order["size"] == -37 and abs(float(tp_order["price"]) - (ta["entry"] + 0.01)) < 1e-6
X_.fill(ta["real"]["tp_id"])           # the take fills: the position goes
V.dlm_real_tick(); V.dlm_real_tick()
win = ta["status"] == "CLOSED" and ta["result"] == "WIN" and ta["r"] > 0
tb_["until"] = time.time() - 1          # the second trade runs out of time
V.dlm_real_tick()
tx = tb_["status"] == "CLOSED" and tb_["result"] == "TIME_EXIT" and "BBB_USDT" in closed
c["until"] = time.time() - 1            # the third order is never filled
V.dlm_real_tick()
cx = c["status"] in ("EXPIRED", "CANCELLED") and X_.orders[c["real"]["id"]]["status"] == "finished"
left = [k for k, v in X_.trig.items()]
cap0 = V.DLM_MAX_POS; V.DLM_MAX_POS = 0
d_ = mk("DDD_USDT", 1, 4.0); V._DLM["orders"].append(d_); V.dlm_real_place(d_)
capped = not d_.get("real"); V.DLM_MAX_POS = cap0
print(f"(4) placed at 4% {placed} · exits {exits_ok} · take = reduce-only limit {bool(tp_ok)} · WIN {win} (R {ta['r']}) · time exit {tx} · unfilled cancelled {cx} · triggers left {left} · position cap {capped}")
ok &= placed and exits_ok and bool(tp_ok) and win and tx and cx and not left and capped
print("ALL OK" if ok else "FAILED"); sys.exit(0 if ok else 1)
