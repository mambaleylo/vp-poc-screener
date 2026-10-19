"""v0.99.641 — P/R: the stop by the bar's close + the hard stop, and the BTC filter (24 h; v0.99.642 + 1 h) (mocked candles / exchange)."""
import sys, io, contextlib, os
sys.argv = ["x"]
sys.path.insert(0, os.environ.get("BOT", "/home/user/vp-poc-screener"))
with contextlib.redirect_stdout(io.StringIO()):
    import vp_poc_screener as V
ok = bad = 0
def check(name, cond):
    global ok, bad
    ok += bool(cond); bad += (not cond)
    print(("OK  " if cond else "FAIL") + " " + name)
V.prx_save = lambda: None
V.send_telegram = lambda *a, **k: None
V.notify_trade_result = lambda *a, **k: None
closed = []
V.close_position_for_mode = lambda mode, sym, d: closed.append((mode, sym, d)) or "closed"
M = {"rule": {"stop_atr": 3.0, "take_r": 1.5, "hold_bars": 48, "hard_atr": 6.0, "stop_close": True}, "btc_filter": 4.0, "btc_filter_1h": 1.0}
H0 = 1_800_000_000 // 3600 * 3600
def mk(open_, rows):   # rows: (high, low, close) per 1h bar from H0
    out, o = [], open_
    for k, (h, l, c) in enumerate(rows):
        out.append({"time": H0 + k * 3600, "open": o, "high": h, "low": l, "close": c}); o = c
    return out
def run(rows, side=1, real=False, rule=M):
    V._PRX["trades"] = []
    V.AUTOTRADE_ENABLED_PRV = False
    V.prx_open(rule, {"side": side, "symbol": "AAA_USDT", "tf": 1, "score": 1.0, "atr": 1.0, "px": 100.0}, H0)
    t = V._PRX["trades"][0]
    if real:
        t["real"] = True; V.AUTOTRADE_ENABLED_PRV = True
    cs = mk(100.0, rows)
    V.get_candles_range = lambda sym, tf, a, b: cs
    V.prx_settle(H0 + len(rows) * 3600 + 60)
    V.AUTOTRADE_ENABLED_PRV = False
    return t
t = run([(101, 96.5, 99)])
check("opened with soft 3 / hard 6 / take 4.5 ATR", t["sl"] == 97 and t["hs"] == 94 and t["tp"] == 104.5 and t["risk"] == 6.0 and t["soft"] == 3.0)
check("a wick through the stop with the close back inside: still open", t["status"] == "OPEN")
t = run([(101, 96.5, 99), (99, 96, 96.5)])
check("the close beyond the stop: STOP_CLOSE at the close", t["status"] == "CLOSED" and t["result"] == "STOP_CLOSE" and t["exit"] == 96.5)
check("R per the hard stop", abs(t["r"] - (96.5 - 100 - 100 * V.PRX_FEE - 100 * V.PRX_FUND * 2 / 24) / 6.0) < 1e-3)
t = run([(101, 93.5, 99)])
check("the hard stop inside the bar: HARD_STOP", t["result"] == "HARD_STOP" and t["exit"] == 94)
t = run([(105, 98, 104)])
check("the take: WIN at 4.5 ATR", t["result"] == "WIN" and t["exit"] == 104.5)
t = run([(104, 98, 101)], side=-1)
check("short: a wick up through the stop, the close back: open", t["status"] == "OPEN" and t["sl"] == 103 and t["hs"] == 106)
t = run([(99, 97, 98), (104, 99, 103.5)], side=-1)
check("short: the close beyond the stop: STOP_CLOSE", t["result"] == "STOP_CLOSE" and t["exit"] == 103.5)
closed.clear(); t = run([(101, 96.5, 99), (99, 96, 96.5)], real=True)
check("a real trade: the stop by close closes the position at market", closed == [("prv", "AAA_USDT", "LONG")])
closed.clear(); t = run([(101, 93.5, 99)], real=True)
check("a real trade: the hard stop is the exchange's own, no market close", closed == [])
old = {"rule": {"stop_atr": 3.0, "take_r": 1.5, "hold_bars": 48}}
t = run([(101, 96.5, 99)], rule=old)
check("an old-rule trade: the stop on touch", t["result"] == "LOSS" and t["exit"] == 97 and "hs" not in t)
# the exchange order gets the hard stop
calls = []
V.execute_autotrade = lambda mode, sym, d, px, sl, tp, **k: calls.append((sl, tp)) or {"status": "OPENED"}
V._PRX["trades"] = []; V.AUTOTRADE_ENABLED_PRV = True
V.prx_open(M, {"side": 1, "symbol": "AAA_USDT", "tf": 1, "score": 1.0, "atr": 1.0, "px": 100.0}, H0, live_px=100.0)
V.AUTOTRADE_ENABLED_PRV = False
check("the exchange stop = the hard stop, sized on it", calls == [(94.0, 104.5)])
# the BTC filter in the scan
ib = len(V.PRX_BAND_NAMES) + V.NX_NAMES.index("b_r24")
i1 = len(V.PRX_BAND_NAMES) + V.NX_NAMES.index("b_r1")
def feats(b24, b1=0.0):
    x = [0.0] * (len(V.PRX_BAND_NAMES) + len(V.NX_NAMES)); x[ib] = b24; x[i1] = b1; return x
EV = {"L1_USDT": [(1, 1, feats(-5.0), 1.0, 10.0)], "L2_USDT": [(1, 1, feats(-3.0), 1.0, 10.0)],
      "S1_USDT": [(1, -1, feats(+4.5), 1.0, 10.0)], "S2_USDT": [(1, -1, feats(-6.0), 1.0, 10.0)],
      "L3_USDT": [(1, 1, feats(-1.0, -1.2), 1.0, 10.0)], "L4_USDT": [(1, 1, feats(-1.0, -0.8), 1.0, 10.0)],
      "S3_USDT": [(1, -1, feats(0.0, +1.5), 1.0, 10.0)]}
V.prx_model = lambda: {"models": {"1": [None], "-1": [None]}, "thr": {"1": 0.5, "-1": 0.5}, "side_cap": 12, **M}
V.zm_tree_pred = lambda t_, x: 1.0
V._own_top_syms = lambda n: list(EV)
V.prx_coin_events = lambda sym, now, ref, th: EV[sym]
V._zm_closed = lambda *a, **k: []
V.get_tickers = lambda: []
opened = []
V.prx_open = lambda m, c, th, px=None: opened.append(c["symbol"])
V.prx_scan_once()
check("BTC filter: 24 h -5% / +4.5% and 1 h -1.2% / +1.5% against skipped", sorted(opened) == ["L2_USDT", "L4_USDT", "S2_USDT"])
check("BTC filter: the skips counted in the scan", V._PRX["scan"]["btc_skip"] == 4 and V._PRX["scan"]["signals"] == 3)
print(f"{ok}/{ok + bad}")
