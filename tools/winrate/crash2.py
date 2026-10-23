"""⚡ 4h crash protection: the deployed mix (q0.99, 20 a side), then causal limits — new orders a side per 4h bar / per
UTC day, a pause of a side after k stops within 24 h; money at 20 positions x 4% (cautious / harsh), the drawdown"""
import os; os.environ["TFH"] = "4"
import numpy as np, warnings, datetime as dt; warnings.filterwarnings("ignore")
exec(open("best_money.py").read().split("za = np.load")[0])
za = np.load("s25_sc_4h_w1_0_A_base.npz", allow_pickle=True); zb = np.load("s25_sc_4h_w1_0_A_0-1-2-5-8.npz", allow_pickle=True)
ta, tb_ = za["THR"].item(), zb["THR"].item()
SC = (za["SC"] + zb["SC"]) / 2; THR = {Y: (ta[Y] + tb_[Y]) / 2 for Y in ta}
def select_x(q, cap, nbar=99, nday=99, k=99, pause=86400, sub=None):
    T, S, SYM, K = D["t"], D["side"], D["sym"], D["K"][0]; Rr = D["R"][0]
    yr = T.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970
    thr = np.full(len(T), np.inf)
    for Y, v in THR.items(): thr[yr == Y] = np.quantile(v, q)
    idx = np.flatnonzero(sub & np.isfinite(SC) & (SC >= thr))
    o = idx[np.lexsort((-SC[idx], T[idx]))]
    busy = {}; act = []; out = []; nb = {}; nd = {}; stops = {1: [], -1: []}; paused = {1: -1, -1: -1}
    for i in o:
        t = T[i]; s = int(S[i]); key = (SYM[i], s)
        if busy.get(key, 0) > t: continue
        for sd in (1, -1):   # stops known by t (exit before t)
            rec = [x for x in stops[sd] if x <= t and x > t - 86400]
            if len(rec) >= k and paused[sd] < t:
                paused[sd] = max(rec) + pause
        if paused[s] > t: continue
        if nb.get((t, s), 0) >= nbar or nd.get((t // 86400, s), 0) >= nday: continue
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == s) >= cap: continue
        end = t + int(K[i]) * 3600; busy[key] = end; act.append((end, s)); out.append(i)
        nb[(t, s)] = nb.get((t, s), 0) + 1; nd[(t // 86400, s)] = nd.get((t // 86400, s), 0) + 1
        if Rr[i] < -0.5: stops[s].append(end)
    return np.array(out, dtype=np.int64)
roll = np.arange(ts(2024), ts(2025, 10) + 1, 7 * 86400.0)
V = [("как сейчас", {}), ("≤2 за свечу", {"nbar": 2}), ("≤3 за свечу", {"nbar": 3}), ("≤5 за свечу", {"nbar": 5}), ("≤10 за день", {"nday": 10})]
for nm, kw in V:
    sel = select_x(0.99, 20, sub=~D["usdc"], **kw); sel = sel[D["t"][sel] >= ts(2022)]
    t0 = D["t"][sel].astype(float); o = np.argsort(t0); sel = sel[o]; t0 = t0[o]
    t1 = t0 + D["K"][0][sel] * 3600.0; R = D["R"][0][sel].astype(float); ST = np.clip(2 * D["F"][sel, 2].astype(float) / 100, 0.002, 0.5)
    W = D["W"][0][sel]; un = (D["chk"] | D["new"])[sel]
    for rk in (0.04, 0.06, 0.08, 0.10):
     res = {}
     for sh, lab in ((-0.025, "c"), (-0.04, "h")):
        y = np.array([sim(t0, t1, R, ST, int(np.searchsorted(t0, s)), s + 365 * 86400.0, 20, rk, sh) for s in roll])
        m3 = np.array([sim(t0, t1, R, ST, int(np.searchsorted(t0, s)), s + 91 * 86400.0, 20, rk, sh)[0] for s in roll])
        res[lab] = (np.median(y[:, 0]), np.percentile(y[:, 0], 10), np.median(y[:, 1]), np.percentile(y[:, 1], 90), np.mean(m3 < 100))
     c, h = res["c"], res["h"]
     print(f"{nm:14s} риск {rk*100:.0f}% n{len(sel)} | медиана ${c[0]:,.0f} 10% ${c[1]:,.0f} просадка {c[2]*100:.0f}%/{c[3]*100:.0f}% 3м<$100 {c[4]*100:.0f}% | жёстко ${h[0]:,.0f} 10% ${h[1]:,.0f}", flush=True)
