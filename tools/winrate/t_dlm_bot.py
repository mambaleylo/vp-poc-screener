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
    V.RESEARCH_COINS_211 = V.RESEARCH_COINS_127 = (t["s"],); V._research_syms = lambda coins, n=300, mode=None: list(coins)
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
# (3b) v0.99.710 — a bot started mid-bar (another phone): the catch-up scans of the last alive bars make the orders of a
# bar already closed again; run twice — no copies
t = picks[0]; bs = 7200 if t["st"] == "close2h" else 14400
V.RESEARCH_COINS_211 = V.RESEARCH_COINS_127 = (t["s"],); V._DLM.update({"orders": [], "trades": []})
V.dlm_catch_up(now=t["t"] + bs + 600)
n1 = len(V._DLM["orders"]); got = [x for x in V._DLM["orders"] if x["side"] == t["d"] and x.get("st") == t["st"] and abs(x["lv"] / t["lv"] - 1) < 1e-4]
V.dlm_catch_up(now=t["t"] + bs + 600)
cu_ok = bool(got) and got[0]["until"] == t["t"] + 4 * bs and len(V._DLM["orders"]) == n1
print(f"(3b) catch-up at the start: the order of a bar closed before {bool(got)} · no copies on a second run {len(V._DLM['orders']) == n1} {cu_ok}")
# v0.99.715 — the catch-up's orders not armed before the loop's settle checked their past bars ("cu"), then the flag off
w = [x for x in V._DLM["orders"] if x["status"] == "OPEN"]
# v0.99.716 — each checked at once: not reached on its closed 1h candles -> no "cu" (armed right away), reached -> "cu" kept
cu2 = (bool(w) and all(x.get("from_cu") and x.get("cu_chk") for x in w) and V._DLM.get("cu_settle") is True
       and all(bool(x.get("cu")) == (V._dlm_hit(x, time.time()) is not False) for x in w) and got and got[0].get("cu"))   # the backtest's order: reached
print("   catch-up orders:", len(w), "kept for the settle:", sum(1 for x in w if x.get("cu")))
V._DLM.pop("cu_settle", None)
# ... and an order its price never reached: armable at once (the scan faked: one reached copy, one far level)
_scan0 = V.dlm_scan
def _fake_scan(t_bar, st, cu=False):
    if st["name"] != got[0]["st"] or t_bar != got[0]["t0"]: return
    for tag, k in (("near", 1.0), ("far", 0.01 if got[0]["side"] > 0 else 100.0)):
        V._DLM["orders"].append(dict(got[0], id=got[0]["id"] + tag, lv=got[0]["lv"] * k, status="OPEN", cu=True, from_cu=True, cu_chk=False, real=None))
V.dlm_scan = _fake_scan; V.dlm_catch_up(now=t["t"] + bs + 600); V.dlm_scan = _scan0; V._DLM.pop("cu_settle", None)
o_near = next(x for x in V._DLM["orders"] if x["id"] == got[0]["id"] + "near"); o_far = next(x for x in V._DLM["orders"] if x["id"] == got[0]["id"] + "far")
cu3 = o_near.get("cu") is True and not o_far.get("cu") and o_far.get("cu_chk")
print(f"   reached -> waits for the settle {o_near.get('cu') is True} · never reached -> armable at once {not o_far.get('cu')}"); cu2 = cu2 and cu3
print(f"(3c) catch-up orders wait for the settle: {cu2}"); cu_ok = cu_ok and cu2
ok &= cu_ok
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
risks = []; sms = []; _crbp = V.compute_risk_based_position
V.compute_risk_based_position = lambda *a, **k: (risks.append(k.get("risk_pct")), sms.append(k.get("safety_margin")), (50.0, 10, None))[2]
V.compute_contracts_from_margin = lambda *a, **k: (37, 1, 50.0, None)
V.set_leverage = lambda *a, **k: None
V.get_tickers = lambda: []
closed = []
V.close_position_for_mode = lambda mode, sym, d: (closed.append(sym), X_.pos.__setitem__(sym, 0), {"ok": True})[2]
V.notify_trade_result = lambda *a, **k: None
TG = []; V.send_telegram = lambda msg, *a, **k: TG.append(msg); V.TELEGRAM_ALERTS_DLM = True   # v0.99.705 — the fill's message
V.AUTOTRADE_DRY_RUN = False; V.AUTOTRADE_ENABLED_DLM = True; V.MODULE_RISK_PCT["dlm"] = None
V._DLM.update({"orders": [], "trades": []})
now = time.time(); tb = int(now // 14400 * 14400)
mk = lambda sym, side, lv: {"id": f"dlm_{sym}_{side}_{tb}", "symbol": sym, "side": side, "lv": lv, "atr": 0.01, "score": 0.5, "t0": tb, "bs": 14400,
                            "until": tb + 4 * 14400, "px": lv + side * 0.02, "status": "OPEN", "real": None}
a, b_, c = mk("AAA_USDT", 1, 1.0), mk("BBB_USDT", -1, 2.0), mk("CCC_USDT", 1, 3.0)
V._DLM["orders"] += [a, b_, c]
for o in (a, b_, c): V.dlm_real_place(o)
placed = (all((o.get("real") or {}).get("id") for o in (a, b_, c)) and risks and all(abs(r - V.dlm_risk() * 0.625 * 1.5) < 1e-3 for r in risks)   # the risk (4.5% v0.99.718) x 0.625 (few open) x 3 / 2 at the emergency stop
          and all(abs(o["real"]["risk"] - V.dlm_risk() * 0.625) < 0.01 for o in (a, b_, c)))
# v0.99.703 — the load: 5+ open -> x1.25, fewer -> x0.625; the old 4h-less trades (bs 900) not counted
_tr0 = V._DLM["trades"]
V._DLM["trades"] = [{"status": "OPEN", "bs": 14400}] * 4 + [{"status": "OPEN", "bs": 900}] * 3
m_lo = V.dlm_load_mult()
V._DLM["trades"] = [{"status": "OPEN", "bs": 14400}] * 5
m_hi = V.dlm_load_mult()
V._DLM["trades"] = _tr0
load_ok = m_lo == 0.625 and m_hi == 1.25
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
ti = next(t for t in V._DLM["trades"] if t["symbol"] == "III_USDT")
h0 = int(time.time()) // 14400 * 14400 - 3 * 3600   # v0.99.694 — the hours h0, h0+1h; h0+2h ends a 4h candle (UTC)
ti["t1h"] = h0; ti["cs_bar"] = 0
H1K["III_USDT"] = [{"time": h0, "open": 4.0, "high": 4.025, "low": 3.99, "close": 4.005},   # a wick to 4.025 (> the stop 4.02), the close back
                   {"time": h0 + 3600, "open": 4.005, "high": 4.026, "low": 4.0, "close": 4.022}]   # an hour closes beyond 4.02 — not a 4h close
V.dlm_real_tick()
wick_ok = ti["status"] == "OPEN" and ti.get("ch") == 4   # the 4h stream: the stop on its chart's 4h close
H1K["III_USDT"].append({"time": h0 + 7200, "open": 4.022, "high": 4.03, "low": 4.01, "close": 4.021})   # the 4h candle closes beyond 4.02
ti["cs_bar"] = h0 - 30   # due again: the three hours looked at
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
print(f"(4) load x0.625/x1.25 {load_ok} · placed at 4% {placed} · exits {exits_ok} · take 1.1 ATR + the emergency stop 3 ATR {bool(tp_ok)} · WIN {win} · a 4h close beyond the stop -> out (a wick / a 1h close: no) {cstop} (R {ta['r']}) · time exit {tx} · unfilled cancelled {cx} · triggers left {left} · position cap {capped} · armed near the price / waits far / no room at the touch -> none / off when far {late_ok}")
ok &= load_ok and placed and exits_ok and bool(tp_ok) and cstop and win and tx and cx and not left and capped and late_ok
# (5) v0.99.694 — the leverage: the liquidation at the model's "liq_buf" x the emergency stop's distance (the backtest's money
# uses the same); the deployed model's value, a lower one -> more leverage, less margin
m_ = V._DLM.get("model") or {}; buf0 = m_.get("liq_buf")
V._DLM["model"] = dict(m_, liq_buf=1.5); l15 = _crbp("LONG", 1.0, 0.94, 50, 0.4, 1000, risk_pct=6, safety_margin=V._dlm_liq_buf())
V._DLM["model"] = dict(m_, liq_buf=1.25); l125 = _crbp("LONG", 1.0, 0.94, 50, 0.4, 1000, risk_pct=6, safety_margin=V._dlm_liq_buf())
V._DLM["model"] = m_
lev_ok = buf0 == V.dlm_model().get("liq_buf") and sms and all(x == buf0 for x in sms) and l15[2] is None and l125[2] is None and l125[1] > l15[1] and l125[0] < l15[0]
print(f"(5) the model's liquidation buffer {buf0}: leverage at 1.5x {l15[1]}, at 1.25x {l125[1]} (margin ${l15[0]:.0f} -> ${l125[0]:.0f}) {lev_ok}")
ok &= lev_ok
# (6) v0.99.704 — the risk by the daily WaveTrend: the bot's wt1 (its last 300 closed daily bars) == the research's (all of
# the history, gh_dlm.json) on pool trades; the multiplier by the model's osc_risk; the real order's risk x it
def daily(sym):
    a = load1h(sym); T = np.array([c["time"] for c in a]); d = T // 86400; out = []
    for k in np.unique(d):
        ix = np.flatnonzero(d == k)
        if len(ix) == 24:
            out.append({"time": int(k * 86400), "open": a[ix[0]]["open"], "high": max(a[i]["high"] for i in ix),
                        "low": min(a[i]["low"] for i in ix), "close": a[ix[-1]]["close"]})
    return out
osc = (V._DLM.get("model") or {}).get("osc_risk") or {}
G = [g for g in json.load(open("gh_dlm.json")) if g]
pick = [G[i] for i in np.random.default_rng(7).choice(len(G), 40, replace=False)]
DCACHE = {}; worst_wt = 0.0; mult_ok = True; n_up = n_dn = 0
for g in pick:
    src, scl = g["sym"], 1.0   # the pool's Binance names (WaveTrend is scale-free)
    if src not in DCACHE: DCACHE[src] = daily(src)
    b = [c for c in DCACHE[src] if c["time"] + 86400 <= g["te"]][-300:]
    w_bot = V._wt1([c["high"] for c in b], [c["low"] for c in b], [c["close"] for c in b]); w_res = g["wt_1d"] * g["d"]
    worst_wt = max(worst_wt, abs(w_bot - w_res))
    V.get_candles_range = lambda sym, tf, a_, z_, b=b: scaled(b, scl) if tf == "1d" else []
    V._OSC.clear(); m = V.dlm_osc_mult(g["sym"], g["d"], now=g["te"])
    x = g["wt_1d"]; want = osc["up"] if x <= osc["lo"] else (osc["dn"] if x >= osc["hi"] else 1.0)
    if abs(x - osc["lo"]) > 0.5 and abs(x - osc["hi"]) > 0.5: mult_ok &= m == want
    n_up += m == osc["up"]; n_dn += m == osc["dn"]
_om = V.dlm_osc_mult; V.dlm_osc_mult = lambda sym, side, now=None: 1.25
_o0, _t0 = V._DLM["orders"], V._DLM["trades"]; V._DLM["orders"], V._DLM["trades"] = [], []
risks.clear(); d_ = mk("DDD_USDT", 1, 4.0); V._DLM["orders"].append(d_); V.dlm_real_place(d_)
want_r = V.dlm_risk() * V.dlm_load_mult() * 1.25 * 1.5
placed_osc = bool((d_.get("real") or {}).get("id")) and risks and abs(risks[-1] - want_r) < 1e-3 and d_["real"].get("osc") == 1.25 and a["real"].get("osc") == 1.0
V.dlm_osc_mult = _om; V._DLM["orders"], V._DLM["trades"] = _o0, _t0
osc_ok = bool(osc) and worst_wt < 0.5 and mult_ok and n_up > 0 and n_dn > 0 and placed_osc
print(f"(6) daily WaveTrend: bot vs research max diff {worst_wt:.3f} on 40 pool trades · multiplier by the model ({osc}) {mult_ok} (x{osc.get('up')} {n_up}, x{osc.get('dn')} {n_dn}) · the real order's risk x it {want_r:.4f}% {placed_osc} {osc_ok}")
ok &= osc_ok
# (7) v0.99.705 — Telegram: no message for the new orders (dlm_scan sends nothing), a filled limit -> the indicator, the
# stream, the fill, take / stop / emergency stop and the risk with its multipliers
import inspect
fills = [m for m in TG if "исполнилась" in m]
f0 = next((m for m in fills if "AAA" in m), "")
tg_ok = ("send_telegram" not in inspect.getsource(V.dlm_scan) and not any("лимитки 4h" in m or "лимитки 2h" in m for m in TG)
         and "⚡ Лимитки (4ч, лимитка на фитиль)" in f0 and "тейк" in f0 and "аварийный" in f0 and "оценка модели" in f0 and f"риск {round(V.dlm_risk() * 0.625, 2):g}%" in f0 and "загрузка ×0.625" in f0)
print(f"(7) Telegram: orders silent, a fill told {tg_ok}\n" + f0)
ok &= tg_ok
print("ALL OK" if ok else "FAILED"); sys.exit(0 if ok else 1)
