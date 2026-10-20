"""v0.99.663: the bot's nx_settle with the limit entry = nx_lim.sim on the same Binance candles (150 random signals)"""
import bisect, numpy as np
from common import V as vp, load
import nx_h as N
from nx_lim import sim
H1 = {}
def rng_(sym, tf, a, b):
    s = sym.replace("_", "")
    if s not in H1: h = load(s); H1[s] = (h, [c["time"] for c in h])
    h, ts = H1[s]; return h[bisect.bisect_left(ts, a):bisect.bisect_right(ts, b)]
vp.get_candles_range = rng_
for f in ("send_telegram", "nx_save", "notify_trade_result"): setattr(vp, f, lambda *a, **k: None)
vp.AUTOTRADE_ENABLED_NEURO = False
rng = np.random.default_rng(2); ok = bad = 0; nofill = 0
for s in (1, -1):
    rows = N.cand(s, 0.995)
    for r in rng.choice(rows, 75, replace=False):
        sym = N.SYMS[int(N.SY[r])]
        if sym.startswith("1000"): continue
        O, H, L, C, atr = N.bars(int(N.SY[r])); i = int(N.I[r]); a = float(atr[i])
        if i + 20 >= len(C) or a != a: continue
        R, K = sim(O, H, L, C, i, s, a, 0.3, 3)
        cs = load(sym); hour = cs[i + 1]["time"]
        tr = {"id": "x", "symbol": sym.replace("USDT", "_USDT"), "side": s, "direction": "LONG" if s > 0 else "SHORT", "hour": hour, "score": 1, "risk": a,
              "entry": None, "sl": None, "tp": None, "px": O[i + 1], "until": hour + 12 * 3600, "hold": 12, "take_r": 3.0, "status": "PENDING", "real": False,
              "atr": a, "lim_atr": 0.3, "wait": 3, "lv": O[i + 1] - s * 0.3 * a}
        vp._NX["trades"] = [tr]
        vp.nx_settle(hour + 20 * 3600)
        if R != R:
            good = tr["result"] == "NO_FILL"; nofill += good
        else:
            good = tr["status"] == "CLOSED" and tr["r"] is not None and abs(tr["r"] - R) < 0.01
        ok += good; bad += not good
        if not good: print(sym, s, R, tr.get("result"), tr.get("r"))
print("neuro ok", ok, "bad", bad, "(no fill ok", nofill, ")")
