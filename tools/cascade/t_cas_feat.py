"""the bot's cas_event (on the last 1000 closed bars) vs the research's event features (cas_ev.py), random events"""
import numpy as np
from common import V, load, D
z = np.load(f"{D}/cas_all.npz"); X, T, SY = z["X"], z["T"], z["SY"]
import glob, os
SYMS = [os.path.basename(f)[:-4] for f in sorted(glob.glob(f"{D}/cas/*.npz"))]
btc = load("BTCUSDT"); btt = [c["time"] for c in btc]
rng = np.random.default_rng(5); bad = 0; n = 0; worst = np.zeros(8)
for r in rng.choice(len(T), 300, replace=False):
    sym = SYMS[SY[r]]; cs = load(sym); t = int(T[r])
    i = next(k for k, c in enumerate(cs) if c["time"] + 3600 == t)
    if i < 1300: continue
    j = int(np.searchsorted(btt, t - 3600))
    ev = V.cas_event(cs[i - 999:i + 1], btc[j - 999:j], t)
    n += 1
    if not ev or ev[0] != int(X[r, 0]): bad += 1; print("miss", sym, t, ev and ev[0], X[r, 0]); continue
    d = np.abs(np.array(ev[1]) - X[r, 1:9]) / np.maximum(1e-9, np.abs(X[r, 1:9]) + 1e-3)
    worst = np.maximum(worst, d)
    if d.max() > 0.01: bad += 1; print(sym, t, np.round(ev[1], 3), np.round(X[r, 1:9], 3))
print("checked", n, "bad", bad, "worst rel diff", np.round(worst, 4))
