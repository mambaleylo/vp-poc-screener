"""the ⚡ tab's money numbers for v0.99.704: the load rule x the daily WaveTrend rule (dynrisk4's sim)"""
src = open("dynrisk4.py").read()
exec(src.split("for nm, lv, rk in")[0])
import json
G = json.load(open("gh_dlm.json")); assert len(G) == len(P)
wt = np.array([g["wt_1d"] if g else np.nan for g in G])
osc = np.where(wt <= -3, 1.25, np.where(wt >= 22, 0.85, 1.0))
lv = np.array([4]); rk = np.array([2.5, 5.0]) / 100
W0 = np.array([rk[int(np.searchsorted(lv, n, side="right"))] for n in NOPEN]) / 0.04
for nm, W in (("v703", W0), ("v704", W0 * osc)):
    y = np.array([sim_w(T0_, T1_, R_, ST_, STH_, W, int(np.searchsorted(T0_, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.025) for s_ in roll])
    yh = np.array([sim_w(T0_, T1_, R_, ST_, STH_, W, int(np.searchsorted(T0_, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.04)[0] for s_ in roll])
    m6 = np.array([sim_w(T0_, T1_, R_, ST_, STH_, W, int(np.searchsorted(T0_, s_)), s_ + 182 * 86400.0, 20, 0.04, -0.025)[0] for s_ in roll])
    l12 = sim_w(T0_, T1_, R_, ST_, STH_, W, int(np.searchsorted(T0_, ts(2025, 10))), ts(2026, 10), 20, 0.04, -0.025)
    print(nm, "MONEY", json.dumps({"year_median": int(np.median(y[:, 0])), "year_p10": int(np.percentile(y[:, 0], 10)), "harsh_median": int(np.median(yh)),
                               "dd": int(round(np.median(y[:, 1]) * 100)), "m6_below": int(round((m6 < 100).mean() * 100)), "m6_median": int(np.median(m6)), "last12": int(l12[0])}), flush=True)
