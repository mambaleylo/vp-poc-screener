"""📈 range breakout: the bot's daily signal and trade record on the history = the research's (rb_daily.py)"""
import pickle, numpy as np
from common import V as vp, load, D
import rb_daily as R
CS = {}
def d1_of(sym):
    if sym not in CS:
        CS[sym] = vp._oc_agg(load(sym), 24)
    return CS[sym]
vp._zm_closed = lambda sym, tf, sec, n, now: [c for c in d1_of(sym.replace("_", "")) if c["time"] + sec <= now][-n:]
vp.get_candles_range = lambda sym, tf, a, b: [c for c in d1_of(sym.replace("_", "")) if a <= c["time"] <= b]
vp.send_telegram = lambda *a, **k: None
vp.rbx_save = lambda: None
vp.notify_trade_result = lambda *a, **k: None
vp.AUTOTRADE_ENABLED_RBX = False
si, xi = R.STOPS.index(1.5), R.EXITS.index("dc20")
ok = bad = 0; tok = tbad = 0; neg_ok = neg_bad = 0
rng = np.random.default_rng(3)
for sym in ("SOLUSDT", "LINKUSDT", "DOGEUSDT", "AVAXUSDT", "XRPUSDT", "ADAUSDT", "ETHUSDT", "BNBUSDT"):
    ev = [e for e in pickle.load(open(f"{D}/rb/{sym}.pkl", "rb")) if e[2]["N"] == 20]
    hit = [e for e in ev if e[2]["rg"] < 2.5 and e[2]["own200"] and e[0] >= 1640995200]
    times = {e[0] for e in hit}
    for t, s, f, y in hit:
        side, info = vp.rbx_state(vp._zm_closed(sym, "1d", 86400, 1000, t + 60))
        if side == s:
            ok += 1
        else:
            bad += 1; print("SIG DIFF", sym, t, s, side, f["rg"], info and info["rg"])
        lab = float(y[si, xi, 0])
        if lab == lab:
            vp._RBX["trades"] = []
            vp.rbx_open({"symbol": sym.replace("USDT", "_USDT"), "side": s, "atr": info["atr"], "close": info["close"], "rg": f["rg"], "brk": 1.0}, t)
            vp.rbx_settle(now=t + 200 * 86400)
            tr = vp._RBX["trades"][0]
            if tr["r"] is not None and abs(tr["r"] - lab) < 0.02:
                tok += 1
            else:
                tbad += 1; print("R DIFF", sym, t, s, tr["result"], tr["r"], lab)
    d1 = d1_of(sym)
    for k in rng.choice(np.arange(400, len(d1) - 1), 40, replace=False):
        t = d1[k]["time"] + 86400
        side, info = vp.rbx_state(vp._zm_closed(sym, "1d", 86400, 1000, t + 60))
        if (side != 0) == (t in times):
            neg_ok += 1
        else:
            neg_bad += 1; print("RANDOM DAY DIFF", sym, t, side, t in times)
print("signals ok", ok, "diff", bad, "| random days ok", neg_ok, "diff", neg_bad, "| trades ok", tok, "diff", tbad)
