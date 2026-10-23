"""⚡ 4h pool: the deployed wick stream (s23 w1) + the close-1.5 ATR stream (s20h4 d15), both with the mix recipe (q0.99);
one position per coin & side across the streams, 20 a side in all; money at 20 positions x 4% (cautious / harsh)"""
import os; os.environ["TFH"] = "4"
import numpy as np, warnings; warnings.filterwarnings("ignore")
exec(open("best_money.py").read().split("za = np.load")[0])
from s15_wf import load
import s20h4_engine as E20, s23_engine as E23
def merged(dr, fi):
    a = load(dr, [fi]); b = load(dr + "x", [fi]); n0 = len(a["names"]); X = {}
    for k in a:
        if k == "names": continue
        ax = 1 if k in ("R", "K", "W") else 0
        X[k] = np.concatenate([a[k], (b[k] + n0 if k == "sym" else (np.zeros_like(b[k]) if k == "chk" else b[k]))], axis=ax)
    X["names"] = a["names"] + b["names"]; X["new"] = np.r_[np.zeros(len(a["t"]), bool), np.ones(len(b["t"]), bool)]
    X["usdc"] = np.array([X["names"][k] == "USDCUSDT" for k in X["sym"]])
    return X
S = {"w1": (merged("s23_4h", 2), "s26_s23_4h_w1_0.npz", 0), "d15": (merged("s20h4", 1), "s26_s20h4_d15_1.npz", 1),
     "d2": (merged("s20h4", 0), "s26_s20h4_d2_1.npz", 1)}
EV = {}
for nm, (X, fn, e) in S.items():
    z = np.load(fn, allow_pickle=True); SCx, THx = z["SC"], z["THR"].item()
    for q in (0.985, 0.99):
        sel = select(X, e, SCx, THx, q, 20, ~X["usdc"]); sel = sel[X["t"][sel] >= ts(2022)]
        EV[(nm, q)] = [(int(X["t"][i]), X["names"][X["sym"][i]], int(X["side"][i]), float(SCx[i]), int(X["K"][e][i]), float(X["R"][e][i]),
                        float(np.clip(2 * X["F"][i, 2] / 100, 0.002, 0.5)), int(X["W"][e][i]), bool(X["chk"][i] or X["new"][i])) for i in sel]
def pool(keys, cap=20):
    ev = sorted([x for k in keys for x in EV[k]], key=lambda x: (x[0], -x[3]))
    busy = {}; act = []; out = []
    for x in ev:
        t, sym, s = x[0], x[1], x[2]
        if busy.get((sym, s), 0) > t: continue
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == s) >= cap: continue
        end = t + x[4] * 3600; busy[(sym, s)] = end; act.append((end, s)); out.append(x)
    return out
roll = np.arange(ts(2024), ts(2025, 10) + 1, 7 * 86400.0)
for keys in ([("w1", 0.99)], [("d15", 0.99)], [("w1", 0.99), ("d15", 0.99)], [("w1", 0.99), ("d15", 0.99), ("d2", 0.99)], [("w1", 0.985), ("d15", 0.985)]):
    ev = pool(keys)
    t0 = np.array([x[0] for x in ev], float); t1 = t0 + np.array([x[4] for x in ev]) * 3600.0; R = np.array([x[5] for x in ev]); STv = np.array([x[6] for x in ev])
    W = np.array([x[7] for x in ev]); U = np.array([x[8] for x in ev]); h = t0 >= ts(2025, 10)
    for rk in (0.03, 0.04, 0.05):
        res = {}
        for sh, lab in ((-0.025, "c"), (-0.04, "h")):
            y = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, rk, sh) for s_ in roll])
            m3 = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 91 * 86400.0, 20, rk, sh)[0] for s_ in roll])
            res[lab] = (np.median(y[:, 0]), np.percentile(y[:, 0], 10), np.median(y[:, 1]), np.percentile(y[:, 1], 90), np.mean(m3 < 100))
        c, hh = res["c"], res["h"]
        print(f"{'+'.join(f'{k}@{q}' for k, q in keys):28s} {rk*100:.0f}% n{len(ev)} ({len(ev)/57:.0f}/мес) WR {W.mean()*100:.0f}% {R.mean():+.3f}R (невид {R[U].mean():+.3f}, посл.12м {R[h].mean():+.3f}) | медиана ${c[0]:,.0f} 10% ${c[1]:,.0f} просадка {c[2]*100:.0f}%/{c[3]*100:.0f}% 3м<$100 {c[4]*100:.0f}% | жёстко ${hh[0]:,.0f} 10% ${hh[1]:,.0f}", flush=True)
