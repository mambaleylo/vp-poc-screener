"""📈 range breakout v2: the bot's signals (day and 12h) and trade records (trend exit and half at +2R) on the
history = the research's (rb_tf.py, rbtf24 / rbtf12)"""
import sys, pickle, bisect, numpy as np
from common import V as vp, load, D
import rb_tf as R
H1 = {}
def h1_of(sym):
    if sym not in H1:
        h = load(sym)
        H1[sym] = (h, [c["time"] for c in h], vp._oc_agg(h, 24))
    return H1[sym]
def closed(sym, tf, sec, n, now):
    h, ts, d1 = h1_of(sym.replace("_", ""))
    if tf == "1d":
        return [c for c in d1 if c["time"] + sec <= now][-n:]
    k = bisect.bisect_right(ts, now - sec)
    return h[max(0, k - n):k]
def rng_(sym, tf, a, b):
    h, ts, d1 = h1_of(sym.replace("_", ""))
    if tf == "1d":
        return [c for c in d1 if a <= c["time"] <= b]
    return h[bisect.bisect_left(ts, a):bisect.bisect_right(ts, b)]
vp._zm_closed = closed
vp.get_candles_range = rng_
vp.send_telegram = lambda *a, **k: None
vp.rbx_save = lambda: None
vp.notify_trade_result = lambda *a, **k: None
vp.AUTOTRADE_ENABLED_RBX = False
si = R.STOPS.index(vp.RBX_STOP_ATR)   # v0.99.646: the bot's stop (2 ATR)
TIGHT = (vp.RBX_TIGHT_R, vp.RBX_TIGHT_DC)   # v0.99.647: the labels have no tightening -> off for them, checked apart below
import rb_sim2 as S2
XI = {False: R.EXITS.index("dc20"), True: R.EXITS.index("half2dc20")}
SYMS = sys.argv[1:] or ["SOLUSDT", "LINKUSDT", "DOGEUSDT", "AVAXUSDT", "XRPUSDT", "ETHUSDT"]
rng = np.random.default_rng(5)
for chart, tfh in (("1d", 24), ("12h", 12)):
    cfg = vp.RBX_CHARTS[chart]; sec = tfh * 3600
    ok = bad = tok = tbad = neg_ok = neg_bad = tgok = tgbad = 0
    for sym in SYMS:
        ev = [e for e in pickle.load(open(f"{D}/rbtf{tfh}/{sym}.pkl", "rb")) if e[2]["N"] == cfg["n"]]
        hit = [e for e in ev if e[2]["rg"] < cfg["k"] and e[2]["own200"] and e[0] >= 1640995200]
        times = {e[0] for e in hit}
        for t, s, f, row, y in hit:
            side, info = vp.rbx_state(vp.rbx_bars(sym, chart, t + 60), cfg)
            if side == s:
                ok += 1
            else:
                bad += 1; print("SIG DIFF", chart, sym, t, s, side, round(f["rg"], 3), info and info["rg"])
                continue
            vp.RBX_TIGHT_R = 0.0
            for half in (False, True):
                lab = float(y[si, XI[half], 0])
                if lab != lab:
                    continue
                vp.RBX_HALF = half
                vp._RBX["trades"] = []
                vp.rbx_open({"symbol": sym.replace("USDT", "_USDT"), "side": s, "atr": info["atr"], "close": info["close"],
                             "rg": f["rg"], "brk": 1.0}, chart, t)
                vp.rbx_settle(now=t + (cfg["hold"] + 3) * sec)
                tr = vp._RBX["trades"][0]
                if tr["r"] is not None and abs(tr["r"] - lab) < 0.02:
                    tok += 1
                else:
                    tbad += 1; print("R DIFF", chart, half, sym, t, s, tr["result"], tr["r"], lab)
            # v0.99.647: the trend exit with the channel tightened after +4R = rb_sim2.sim
            vp.RBX_TIGHT_R, vp.RBX_TIGHT_DC = TIGHT; vp.RBX_HALF = False
            vp._RBX["trades"] = []
            vp.rbx_open({"symbol": sym.replace("USDT", "_USDT"), "side": s, "atr": info["atr"], "close": info["close"], "rg": f["rg"], "brk": 1.0}, chart, t)
            vp.rbx_settle(now=t + (cfg["hold"] + 3) * sec)
            tr = vp._RBX["trades"][0]
            O_, H_, L_, C_, T_, A_, LO_, HI_, _ = S2.bars(sym, tfh); j = int(np.searchsorted(T_, t))
            exp, _k, _x = S2.sim(O_, H_, L_, C_, LO_, HI_, j + 1, O_[j + 1], s, float(A_[j]), vp.RBX_STOP_ATR, cfg["hold"], tfh, S2.NEX.index(vp.RBX_DC),
                             TIGHT[0], S2.NEX.index(TIGHT[1]), 0, 0.0)
            if tr["r"] is None and j + 1 + _k >= len(C_) - 1:
                tgok += 1   # still open at the data's end (the research closes it at the last bar)
            elif tr["r"] is not None and abs(tr["r"] - exp) < 0.02:
                tgok += 1
            else:
                tgbad += 1; print("TIGHT DIFF", chart, sym, t, s, tr["result"], tr["r"], round(exp, 3))
        bars = vp._oc_agg(h1_of(sym)[0], tfh)
        for k in rng.choice(np.arange(len(bars) // 3, len(bars) - 1), 40, replace=False):
            t = bars[k]["time"] + sec
            side, info = vp.rbx_state(vp.rbx_bars(sym, chart, t + 60), cfg)
            if (side != 0) == (t in times):
                neg_ok += 1
            else:
                neg_bad += 1; print("RANDOM BAR DIFF", chart, sym, t, side, t in times)
    print(chart, "signals ok", ok, "diff", bad, "| random bars ok", neg_ok, "diff", neg_bad, "| trades ok", tok, "diff", tbad, "| tightened exit ok", tgok, "diff", tgbad, flush=True)
