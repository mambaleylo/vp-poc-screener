"""v0.99.687 — ⚡ 4h wick limits in the bot (v0.99.689: + the 2h close-2ATR stream): (1) features == the research (bot functions); (2) the model file; (3) the
virtual path re-makes backtest trades (scan at the 4h close -> the order at the same level, settle -> the fill and the
same R); (4) the real path on a fake exchange: a GTC limit placed, filled -> the stop trigger + the reduce-only take
limit, the take filled -> WIN; a second trade -> the time exit at the market; an order not filled -> cancelled; at most
DLM_MAX_POS positions. Run from the research folder (common.py, s20h4/ and the data)."""
import sys, json, time, bisect, numpy as np
from common import V
import os; os.environ["TFH"] = "4"
import s23_engine as E
import s21h2_engine as E2
from common import load as load1h
ok = True
def bars(sym, tf="4h"):
    if tf == "1h":
        return [dict(c, volume=c.get("volume", 0)) for c in load1h(sym)]
    T, O, H, L, C, Vv = (E2 if tf == "2h" else E).load15(sym)
    return [{"time": int(t), "open": o, "high": h, "low": l, "close": c, "volume": v} for t, o, h, l, c, v in zip(T, O, H, L, C, Vv)]
CACHE = {}
def series(sym, tf="4h"):
    if (sym, tf) not in CACHE:
        b = bars(sym, tf); CACHE[(sym, tf)] = (b, [c["time"] for c in b])
    return CACHE[(sym, tf)]
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
m = V.dlm_model(); ok &= (bool(m) and m["feats"] == V.DLM_FNAMES4 and m["ver"] == 3 and m["side_cap"] == 20
                          and [(x["name"], x["tf"], x["bar_sec"]) for x in m["streams"]] == [("wick4h", "4h", 14400), ("close2h", "2h", 7200)]
                          and all(len(x["models"]) == 20 for x in m["streams"]))
print("(2) model", bool(m), m and [(x["name"], x["anchor"], x["depth_atr"], x["thr"]) for x in m["streams"]])
# (3) the virtual path on backtest trades (mocked candles from Binance 4h)
BL = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "/home/user/vp-poc-screener/vp_bt_trades.json"))["dlm"]
pool_ = [t for t in BL if t["t"] >= 1767225600 and not t.get("chk")]
picks = [t for st in ("wick4h", "close2h") for k, n in (("take", 2), ("stop", 2), ("time", 1)) for t in [x for x in pool_ if x["k"] == k and x["st"] == st][:n]]
def bname(gs):
    b = gs.replace("_USDT", "")
    for c in (b + "USDT", "1000" + b + "USDT"):
        try: series(c); return c, (1000.0 if c.startswith("1000") else 1.0)
        except Exception: pass
def scaled(lst, scl): return [dict(c, open=c["open"] / scl, high=c["high"] / scl, low=c["low"] / scl, close=c["close"] / scl) for c in lst]
def fake_closed(sym, tf, sec, n, now):
    src, scl = ("BTCUSDT", 1.0) if sym == "BTC_USDT" else bname(sym)
    return scaled([c for c in series(src, tf)[0] if c["time"] + sec <= now][-n:], scl)
def fake_range(sym, tf, a, z_):   # Gate: 4h, or 1h (the bot builds 2h from it — Gate has no 2h)
    src, scl = bname(sym)
    return scaled([c for c in series(src, tf)[0] if a <= c["time"] <= z_], scl)
V._dlm_closed = fake_closed; V.get_candles_range = fake_range; V.bn_closed = lambda *a, **k: None
V.dlm_save = lambda: None; V.heartbeat = lambda *a, **k: None; V.AUTOTRADE_ENABLED_DLM = False; V.DLM_BINANCE = False
hits = 0
for t in picks:
    V.RESEARCH_COINS_211 = V.RESEARCH_COINS_127 = (t["s"],); V._research_syms = lambda coins, n=300: list(coins)
    V._DLM.update({"orders": [], "trades": []})
    V.dlm_scan(t["t"], V._dlm_stream(t["st"]))
    o = [x for x in V._DLM["orders"] if x["side"] == t["d"]]
    bs = 7200 if t["st"] == "close2h" else 14400
    o = [x for x in o if x.get("st") == t["st"]]
    lv_ok = (bool(o) and abs(o[0]["lv"] / t["lv"] - 1) < 1e-4   # the list keeps 10 decimals (SHIB ~1e-5)
             and o[0]["bs"] == bs and o[0]["until"] == t["t"] + 4 * bs)
    V.dlm_settle(t["t"] + 5 * bs + 30)
    V.dlm_settle(t["x"] + bs)
    tr = [x for x in V._DLM["trades"] if x["side"] == t["d"] and x.get("st") == t["st"]]
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
MARK = {"AAA_USDT": 1.0, "BBB_USDT": 2.0, "CCC_USDT": 3.0}
V.get_open_positions = lambda: [{"contract": c, "size": v, "mark_price": str(MARK.get(c, 1))} for c, v in X_.pos.items() if v]
KL = {}   # v0.99.690 — the 1m candles the take watcher reads
H1K = {}   # v0.99.692 — the 1h candles of the close stop
V._dlm_1h = lambda sym, start, now: [c for c in H1K.get(sym, []) if c["time"] >= start and c["time"] + 3600 <= now]
V.binance_klines = lambda sym, iv, a, b: [c for c in KL.get(sym, []) if a <= c["time"] <= b]
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
V.get_tickers = lambda: []
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
placed = (all((o.get("real") or {}).get("id") for o in (a, b_, c)) and risks and all(r == 6.0 for r in risks)   # 4% x 3 / 2 at the emergency stop
          and all(o["real"]["risk"] == 4.0 for o in (a, b_, c)))
X_.fill(a["real"]["id"]); X_.fill(b_["real"]["id"])
V.dlm_real_tick()
ta = next(t for t in V._DLM["trades"] if t["symbol"] == "AAA_USDT"); tb_ = next(t for t in V._DLM["trades"] if t["symbol"] == "BBB_USDT")
exits_ok = bool(ta["real"].get("sl_id") and ta["real"].get("tp_id") and ta["real"].get("tp_kind") == "limit") and ta["hold"] == 32 and ta["until"] - ta["fbar"] == 32 * 14400
tp_order = X_.orders[ta["real"]["tp_id"]]   # v0.99.692 — the take 1.1 ATR, the exchange's stop = the emergency 3 ATR
tp_ok = (tp_order.get("reduce_only") and tp_order["size"] == -37 and abs(float(tp_order["price"]) - (ta["entry"] + 0.011)) < 1e-6
         and abs(X_.trig[str(ta["real"]["sl_id"])][1] - (ta["entry"] - 0.03)) < 1e-6 and abs(ta["sl"] - (ta["entry"] - 0.02)) < 1e-9 and ta.get("smode") == "close1h")
X_.fill(ta["real"]["tp_id"])           # the take fills: the position goes
V.dlm_real_tick(); V.dlm_real_tick()
win = ta["status"] == "CLOSED" and ta["result"] == "WIN" and ta["r"] > 0
# a short whose 1h candle closes beyond the 2 ATR stop: out at the market, LOSS (a wick beyond it and back: nothing)
i_ = mk("III_USDT", -1, 4.0); V._DLM["orders"].append(i_); V.dlm_real_place(i_); X_.fill(i_["real"]["id"]); V.dlm_real_tick()
ti = next(t for t in V._DLM["trades"] if t["symbol"] == "III_USDT"); h0 = int(time.time()) // 3600 * 3600 - 7200
ti["t1h"] = h0; ti["cs_bar"] = 0
H1K["III_USDT"] = [{"time": h0, "open": 4.0, "high": 4.025, "low": 3.99, "close": 4.005}]   # a wick to 4.025 (> the stop 4.02), the close back
V.dlm_real_tick()
wick_ok = ti["status"] == "OPEN"
H1K["III_USDT"].append({"time": h0 + 3600, "open": 4.005, "high": 4.026, "low": 4.0, "close": 4.022})   # the close beyond 4.02
ti["cs_bar"] = h0 - 30   # due again: both hours looked at
V.dlm_real_tick()
cstop = wick_ok and ti["status"] == "CLOSED" and ti["result"] == "LOSS" and ti.get("close_stop") and "III_USDT" in closed
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
# v0.99.691 — the waiting orders go on the exchange as the price comes (_dlm_arm): near -> placed; far -> waits;
# through the level with no room -> no trade
V._DLM["orders"] = [x for x in V._DLM["orders"] if x is not d_]
e_, f_, g_ = mk("EEE_USDT", 1, 5.0), mk("FFF_USDT", 1, 6.0), mk("GGG_USDT", 1, 7.0)
PX = {"EEE_USDT": 5.002, "FFF_USDT": 5.999, "GGG_USDT": 7.05}   # 0.2 ATR above / 0.1 through / 5 ATR above
V.get_tickers = lambda: [{"contract": k, "last": str(v)} for k, v in PX.items()]
V._DLM["orders"] += [e_, g_]
V.dlm_real_tick()
arm_ok = bool((e_.get("real") or {}).get("id")) and g_.get("real") is None
cap0 = V.DLM_MAX_POS; V.DLM_MAX_POS = 0; V._DLM["orders"].append(f_)
V.dlm_real_tick(); V.DLM_MAX_POS = cap0
arm_ok = arm_ok and (f_.get("real") or {}).get("status") == "SKIPPED" and not (f_.get("real") or {}).get("id")
PX["EEE_USDT"] = 5.02   # 2 ATR away: the armed limit comes off, the order waits again
V.dlm_real_tick()
late_ok = arm_ok and e_.get("real") is None and e_["status"] == "OPEN"
print(f"(4) placed at 4% {placed} · exits {exits_ok} · take 1.1 ATR + the emergency stop 3 ATR {bool(tp_ok)} · WIN {win} · a 1h close beyond the stop -> out (a wick: no) {cstop} (R {ta['r']}) · time exit {tx} · unfilled cancelled {cx} · triggers left {left} · position cap {capped} · armed near the price / waits far / no room at the touch -> none / off when far {late_ok}")
ok &= placed and exits_ok and bool(tp_ok) and cstop and win and tx and cx and not left and capped and late_ok
print("ALL OK" if ok else "FAILED"); sys.exit(0 if ok else 1)
