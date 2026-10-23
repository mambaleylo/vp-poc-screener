"""⚡ 4h wick (deployed) + a 2h stream (s21h2 d2 / wick1, the mix recipe), pooled as the bot would trade them: every
event above its stream's threshold places an order, the first of a coin & side to fill is the trade (busy until its
exit), 20 a side; money at 20 positions in that order (the signal time, then the fill, then the score)"""
import os; os.environ["TFH"] = "4"
import numpy as np, warnings; warnings.filterwarnings("ignore")
exec(open("best_money.py").read().split("za = np.load")[0])
from s15_wf import load
import importlib
def merged(dr, fi):
    a = load(dr, [fi]); b = load(dr + "x", [fi]); n0 = len(a["names"]); X = {}
    for k in a:
        if k == "names": continue
        ax = 1 if k in ("R", "K", "W") else 0
        X[k] = np.concatenate([a[k], (b[k] + n0 if k == "sym" else (np.zeros_like(b[k]) if k == "chk" else b[k]))], axis=ax)
    X["names"] = a["names"] + b["names"]; X["usdc"] = np.array([X["names"][k] == "USDCUSDT" for k in X["sym"]])
    return X
def stream(dr, fi, ex, scf, eng, tfh, anchor, depth, q):
    os.environ["TFH"] = str(tfh); E = importlib.import_module(eng)
    X = merged(dr, fi); z = np.load(scf, allow_pickle=True); SC, THR = z["SC"], z["THR"].item(); T = X["t"]
    yr = T.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970; thr = np.full(len(T), np.inf)
    for Y, v in THR.items(): thr[yr == Y] = np.quantile(v, q)
    idx = np.flatnonzero(~X["usdc"] & np.isfinite(SC) & (SC >= thr) & (T >= ts(2022)))
    out, cache = [], {}
    for i in idx:
        sym = X["names"][X["sym"][i]]; s = int(X["side"][i]); t = int(T[i])
        if sym not in cache:
            Tb, O, H, L, C, V = E.load15(sym); cache[sym] = (Tb, H, L, C, E.wilder(H, L, C, 14), {int(x): j for j, x in enumerate(Tb)})
        Tb, H, L, C, atr, pos = cache[sym]; bi = pos[t]; a = float(atr[bi])
        lv = ((L[bi] if s > 0 else H[bi]) if anchor == "wick" else C[bi]) - s * depth * a
        fb = next(b for b in range(bi + 1, bi + 5) if ((L[b] <= lv) if s > 0 else (H[b] >= lv)))
        out.append((t + tfh * 3600, int(Tb[fb]), -float(SC[i]), sym, s, t + int(X["K"][ex][i]) * 3600, float(X["R"][ex][i]), float(np.clip(2 * X["F"][i, 2] / 100, 0.002, 0.5))))
    return out
W4 = stream("s23_4h", 2, 0, "s26_s23_4h_w1_0.npz", "s23_engine", 4, "wick", 1.0, 0.99)
S2 = {"2ч 2ATR": stream("s21h2", 0, 1, "s26_s21h2_d2_1.npz", "s21h2_engine", 2, "close", 2.0, 0.99),
      "2ч тень": stream("s21h2", 2, 1, "s26_s21h2_wick1_1.npz", "s21h2_engine", 2, "wick", 1.0, 0.99)}
def pool(evs):
    ev = sorted(evs, key=lambda x: (x[1], x[2], x[0]))   # by the fill (the first to fill is the trade), then the score — never by the exit
    busy, act, P = {}, [], []
    for t, ft, nsc, sym, s, end, R, st in ev:
        if busy.get((sym, s), 0) > ft: continue
        act = [x for x in act if x[0] > ft]
        if sum(1 for x in act if x[1] == s) >= 20: continue
        busy[(sym, s)] = end; act.append((end, s)); P.append((ft, end, R, st))
    P.sort(key=lambda x: x[0])
    return np.array(P, float)
roll = np.arange(ts(2024), ts(2025, 10) + 1, 7 * 86400.0)
for nm, evs in [("4ч тень (сейчас)", W4)] + [(f"4ч тень + {k}", W4 + v) for k, v in S2.items()] + [(k, v) for k, v in S2.items()]:
    P = pool(evs); t0, t1, R, STv = P[:, 0], P[:, 1], P[:, 2], P[:, 3]
    for rk in (0.03, 0.04, 0.05):
        y = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, rk, -0.025) for s_ in roll])
        yh = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, rk, -0.04)[0] for s_ in roll])
        print(f"{nm:22s} {rk*100:.0f}% n{len(R)} {R.mean():+.3f}R | медиана ${np.median(y[:, 0]):,.0f} 10% ${np.percentile(y[:, 0], 10):,.0f} просадка {np.median(y[:, 1])*100:.0f}%/{np.percentile(y[:, 1], 90)*100:.0f}% | жёстко ${np.median(yh):,.0f}", flush=True)
