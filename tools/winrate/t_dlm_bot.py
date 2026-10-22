"""v0.99.679 — ⚡ 15m deep limits in the bot: (1) features == the research (bot functions); (2) the model file; (3) the
virtual path re-makes backtest trades (scan at the bar close -> the order at the same level, settle -> the fill and
the same R); (4) the real path on a fake exchange: a GTC limit placed, filled -> the stop trigger + the reduce-only take
limit, the take filled -> WIN; a second trade -> the time exit at the market; an order not filled -> cancelled."""
import sys, json, time, bisect, numpy as np
from common import V
import s15_engine as E
ok = True
def bars(sym):
    T, O, H, L, C, Vv = E.load15(sym)
    return [{"time": int(t), "open": o, "high": h, "low": l, "close": c, "volume": v} for t, o, h, l, c, v in zip(T, O, H, L, C, Vv)]
def days(b):
    out = []
    for c in b:
        ps = c["time"] // 86400 * 86400
        if not out or out[-1]["time"] != ps: out.append(dict(c, time=ps))
        else:
            x = out[-1]; x["high"] = max(x["high"], c["high"]); x["low"] = min(x["low"], c["low"]); x["close"] = c["close"]
    return out
CACHE = {}
def series(sym):
    if sym not in CACHE:
        b = bars(sym); CACHE[sym] = (b, [c["time"] for c in b], days(b))
    return CACHE[sym]
# (1) parity through the bot
B, BT, _ = series("BTCUSDT")
rng = np.random.default_rng(5); tot = miss = 0; worst = np.zeros(28)
for sym in ("SOLUSDT", "DOGEUSDT"):
    b, bT, d = series(sym); z = np.load(f"s15/{sym}.npz")
    for k in rng.choice(np.flatnonzero((z["fam"] == 0) & (z["t"] >= 1704067200)), 30, replace=False):
        i = int(z["i"][k]); t = bT[i]; bj = bisect.bisect_right(BT, t)
        cs = V.dlm_candidates(b[max(0, i - 2999):i + 1], [c for c in d if c["time"] + 86400 <= t], B[max(0, bj - 300):bj])
        m = [c for c in cs if c["side"] == int(z["side"][k])]
        tot += 1
        if not m: miss += 1; continue
        worst = np.maximum(worst, np.abs(np.array(m[0]["f"]) - z["F"][k].astype(float)))
print(f"(1) parity {tot} events, missed {miss}, max |diff| {worst.max():.2e}")
ok &= miss == 0 and worst.max() < 1e-4   # the research stores the features as float32
# (2) the model
m = V.dlm_model(); ok &= bool(m) and m["feats"] == V.DLM_FNAMES
print("(2) model", bool(m), m and m["thr"])
# (3) the virtual path on backtest trades (mocked candles from Binance 15m)
BL = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))["dlm"]
picks = [t for t in BL if t["t"] >= 1767225600 and not t.get("chk")][:6]
def bname(gs):
    b = gs.replace("_USDT", "")
    for c in (b + "USDT", "1000" + b + "USDT"):
        try: series(c); return c, (1000.0 if c.startswith("1000") else 1.0)
        except Exception: pass
def scaled(lst, scl): return [dict(c, open=c["open"] / scl, high=c["high"] / scl, low=c["low"] / scl, close=c["close"] / scl) for c in lst]
def fake_closed(sym, tf, sec, n, now):
    src, scl = ("BTCUSDT", 1.0) if sym == "BTC_USDT" else bname(sym)
    b, bT, d = series(src)
    lst = b if tf == "15m" else d
    return scaled([c for c in lst if c["time"] + sec <= now][-n:], scl)
def fake_range(sym, tf, a, z_):
    src, scl = bname(sym); b = series(src)[0]
    return scaled([c for c in b if a <= c["time"] <= z_], scl)
V._dlm_closed = fake_closed; V.get_candles_range = fake_range
V.dlm_save = lambda: None; V.heartbeat = lambda *a, **k: None; V.AUTOTRADE_ENABLED_DLM = False
hits = 0
for t in picks:
    V.RESEARCH_COINS_127 = (t["s"],); V._research_syms = lambda coins, n=300: list(coins)
    V._DLM.update({"orders": [], "trades": []})
    V.dlm_scan(t["t"])
    o = [x for x in V._DLM["orders"] if x["side"] == t["d"]]
    lv_ok = bool(o) and abs(o[0]["lv"] / t["lv"] - 1) < 1e-6
    V.dlm_settle(t["t"] + 5 * 900 + 30)
    V.dlm_settle(t["x"] + 1800)
    tr = [x for x in V._DLM["trades"] if x["side"] == t["d"]]
    r = tr[0]["r"] if tr else None
    same = r is not None and abs(r - t["r"]) < 0.01
    hits += lv_ok and same
    print(f"   {t['s']:12s} {t['d']:+d} order {'✓' if lv_ok else '✗'} · R bot {r} vs backtest {t['r']} {'✓' if same else '✗'}")
print(f"(3) {hits}/{len(picks)}"); ok &= hits >= len(picks) - 1
# (4) the real path on a fake exchange
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
        sz = int(o["size"])
        if o.get("reduce_only"): s.pos[o["contract"]] = s.pos.get(o["contract"], 0) + sz
        else: s.pos[o["contract"]] = s.pos.get(o["contract"], 0) + sz
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
V.compute_risk_based_position = lambda *a, **k: (50.0, 10, None)
V.compute_contracts_from_margin = lambda *a, **k: (37, 1, 50.0, None)
V.set_leverage = lambda *a, **k: None
closed = []
V.close_position_for_mode = lambda mode, sym, d: (closed.append(sym), X_.pos.__setitem__(sym, 0), {"ok": True})[2]
V.notify_trade_result = lambda *a, **k: None
V.send_telegram = lambda *a, **k: None
V.AUTOTRADE_DRY_RUN = False; V.AUTOTRADE_ENABLED_DLM = True
V._DLM.update({"orders": [], "trades": []})
now = time.time(); tb = int(now // 900 * 900)
mk = lambda sym, side, lv: {"id": f"dlm_{sym}_{side}_{tb}", "symbol": sym, "side": side, "lv": lv, "atr": 0.01, "score": 0.1, "t0": tb, "until": tb + 3600, "px": lv + side * 0.02, "status": "OPEN", "real": None}
a, b_, c = mk("AAA_USDT", 1, 1.0), mk("BBB_USDT", -1, 2.0), mk("CCC_USDT", 1, 3.0)
V._DLM["orders"] += [a, b_, c]
for o in (a, b_, c): V.dlm_real_place(o)
placed = all((o.get("real") or {}).get("id") for o in (a, b_, c))
X_.fill(a["real"]["id"]); X_.fill(b_["real"]["id"])
V.dlm_real_tick()
ta = next(t for t in V._DLM["trades"] if t["symbol"] == "AAA_USDT"); tb_ = next(t for t in V._DLM["trades"] if t["symbol"] == "BBB_USDT")
exits_ok = bool(ta["real"].get("sl_id") and ta["real"].get("tp_id") and ta["real"].get("tp_kind") == "limit")
tp_order = X_.orders[ta["real"]["tp_id"]]
tp_ok = tp_order.get("reduce_only") and tp_order["size"] == -37 and float(tp_order["price"]) > ta["entry"]
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
print(f"(4) placed {placed} · exits {exits_ok} · take = reduce-only limit {bool(tp_ok)} · WIN {win} (R {ta['r']}) · time exit {tx} · unfilled cancelled {cx} · triggers left {left}")
ok &= placed and exits_ok and bool(tp_ok) and win and tx and cx and not left
print("ALL OK" if ok else "FAILED"); sys.exit(0 if ok else 1)
