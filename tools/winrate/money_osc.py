"""the ⚡ daily WaveTrend risk multiplier (v0.99.704, the model's osc_risk: the coin's daily WaveTrend 10/21 wt1 x the side
on the last closed day <= lo -> x up, >= hi -> x dn) added to money_expect.py's money (14x, the 2h shorts x0.5): with
and without it. The daily bars from the 1h candles (UTC days), the EMAs over the coin's whole history (the bot's 300 days
settle the same). -> the table + <LABSTORE>/wf/money_osc.json"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import money_multi as M, money_expect as X
from multiprocessing import Pool
OSC = json.load(open("/home/user/vp-poc-screener/vp_dlm_model.json"))["osc_risk"]
def ema(x, n):
    k = 2 / (n + 1); out = np.empty(len(x)); a = x[0]
    for i, v in enumerate(x):
        a = a + k * (v - a); out[i] = a
    return out
WT = {}
def wt_days(sym):
    if sym not in WT:
        a = np.loadtxt(os.path.join(M.DATA, f"{sym}.csv.gz"), delimiter=",", ndmin=2, usecols=(0, 1, 2, 3, 4))
        d = (a[:, 0] // 86400).astype(np.int64); u, i0 = np.unique(d, return_index=True)
        H = np.maximum.reduceat(a[:, 2], i0); L = np.minimum.reduceat(a[:, 3], i0); C = a[np.r_[i0[1:] - 1, len(a) - 1], 4]
        ap = (H + L + C) / 3; esa = ema(ap, 10); dd = ema(np.abs(ap - esa), 10)
        ci = (ap - esa) / np.maximum(0.015 * dd, 1e-12); WT[sym] = (u, ema(ci, 21))
    return WT[sym]
def osc(v):
    if v["mod"] != "dlm": return 1.0
    u, w = wt_days(v["sym"]); day = (v["t0"] - 3600) // 86400   # the last closed day before the touch hour
    j = np.searchsorted(u, day) - 1
    if j < 60: return 1.0
    x = w[j] * v["side"]
    return OSC["up"] if x <= OSC["lo"] else (OSC["dn"] if x >= OSC["hi"] else 1.0)
W_OSC = lambda v: M.W2S(v) * osc(v)
def job(a):
    kind, A, wo = a
    if kind not in M._EV: M._EV[kind] = [v for v in M.build("base") if v["mod"] in X.KINDS[kind]]
    return kind, wo, A, M.run(M._EV[kind], A, A + 365 * 86400, 14.0, W_OSC if wo else M.W2S, eq0=100.0)
if __name__ == "__main__":
    EV = [v for v in M.build("base") if v["mod"] == "dlm"]
    m = np.array([osc(v) for v in EV]); r = np.array([v["r"] for v in EV])
    for k in (OSC["up"], 1.0, OSC["dn"]):
        s = m == k; print(f"⚡ x{k}: {s.sum()} сделок ({s.mean()*100:.0f}%), средний R {r[s].mean():+.3f}", flush=True)
    jobs = [(k, A, wo) for k in ("bundle_htf", "dlm") for wo in (False, True) for A in X.STARTS + [X.LAST]]
    with Pool(4) as P:
        res = P.map(job, jobs, chunksize=4)
    R = {}
    for k, wo, A, rr in res: R.setdefault(f"{k}{' +WT' if wo else ''}", {})[A] = rr
    out = {}
    for key, v in R.items():
        E = np.array([v[A][0] for A in X.STARTS]); dd = np.array([v[A][3] for A in X.STARTS])
        out[key] = {"p10": int(np.percentile(E, 10)), "p50": int(np.median(E)), "p90": int(np.percentile(E, 90)), "dd": int(round(np.median(dd) * 100)),
                    "dd_max": int(round(dd.max() * 100)), "last12": int(v[X.LAST][0])}
        print(key, out[key], flush=True)
    for k in ("bundle_htf", "dlm"):
        a = np.array([R[k][A][0] for A in X.STARTS]); b = np.array([R[k + " +WT"][A][0] for A in X.STARTS])
        print(k, f"с WaveTrend лучше в {int((b > a * 1.001).sum())} из {len(a)} окон, медиана x{np.median(b / a):.2f}", flush=True)
    json.dump(out, open(os.path.join(M.ST, "wf", "money_osc.json"), "w"), indent=1)
