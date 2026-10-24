"""daily oscillator features (GitHub indicators) for every ⚡ candidate: WaveTrend wt1, Ehlers Fisher, EWO, TD count — each x
the side — on the last daily bar closed by the signal's knowledge time (the chart bar's close). Saved as f3_<dir>/<SYM>.npz"""
import sys, os, numpy as np
ARGS = sys.argv[1:]
import gh_lib as GH
TFH = {"s23_4h": 4, "s23_4hx": 4, "s21h2": 2, "s21h2x": 2}
def run(d):
    os.makedirs(f"f3_{d}", exist_ok=True)
    for f in sorted(os.listdir(d)):
        if not f.endswith(".npz") or os.path.exists(f"f3_{d}/{f}"): continue
        z = np.load(f"{d}/{f}"); t = z["t"].astype(np.int64); s = z["side"].astype(float)
        et, st = GH.coin(f[:-4])["1d"]; GH.cache.clear()
        k = np.searchsorted(et, t + TFH[d] * 3600, side="right") - 1
        ok = k >= 60; kk = np.maximum(k, 0)
        F3 = np.full((len(t), 4), np.nan, np.float32)
        for c, nm in enumerate(("wt", "fisher", "ewo", "td")):
            F3[ok, c] = st[nm][kk[ok]] * s[ok]
        np.savez(f"f3_{d}/{f}", t=t, F3=F3)
    print(d, "done", flush=True)
for d in ARGS: run(d)
