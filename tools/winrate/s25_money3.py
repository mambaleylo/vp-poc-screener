import os; os.environ["TFH"] = "4"
import numpy as np, warnings; warnings.filterwarnings("ignore")
import pool as PL, s23_engine as E
from s15_wf import load, select
from mk import ts
def merged():
    a = load("s23_4h", [2]); b = load("s23_4hx", [2]); n0 = len(a["names"]); D = {}
    for k in a:
        if k == "names": continue
        ax = 1 if k in ("R", "K", "W") else 0
        D[k] = np.concatenate([a[k], (b[k] + n0 if k == "sym" else (np.zeros_like(b[k]) if k == "chk" else b[k]))], axis=ax)
    D["names"] = a["names"] + b["names"]; D["new"] = np.r_[np.zeros(len(a["t"]), bool), np.ones(len(b["t"]), bool)]
    D["usdc"] = np.array([D["names"][k] == "USDCUSDT" for k in D["sym"]])
    return D
D = merged()
roll = np.arange(ts(2024), ts(2025, 10) + 1, 7 * 86400.0)
za = np.load("s25_sc_4h_w1_0_A_base.npz", allow_pickle=True); zb = np.load("s25_sc_4h_w1_0_A_0-1-2-5-8.npz", allow_pickle=True)
ta, tb_ = za["THR"].item(), zb["THR"].item()
VARS = {"mix": ((za["SC"] + zb["SC"]) / 2, {Y: (ta[Y] + tb_[Y]) / 2 for Y in ta if Y in tb_ and len(ta[Y]) == len(tb_[Y])})}
for nm, (SC, THR) in VARS.items():
    for q in (0.98, 0.985, 0.99):
        for cap in (20,):
            sub = ~D["usdc"]
            sel = select(D, 0, SC, THR, q, cap, sub); sel = sel[D["t"][sel] >= ts(2022)]
            t0 = D["t"][sel].astype(float); o = np.argsort(t0); sel = sel[o]; t0 = t0[o]
            t1 = t0 + D["K"][0][sel] * 3600.0; R = D["R"][0][sel].astype(float); ST = np.clip(2 * D["F"][sel, 2].astype(float) / 100, 0.002, 0.5)
            W = D["W"][0][sel]; h = t0 >= ts(2025, 10); un = (D["chk"] | D["new"])[sel]
            yr = np.array([PL.multi(t0, t1, R, ST, int(np.searchsorted(t0, s)), s + 365 * 86400.0, 20, 0.03, False, -0.025) for s in roll]) + 100
            m6 = np.array([PL.multi(t0, t1, R, ST, int(np.searchsorted(t0, s)), s + 182 * 86400.0, 20, 0.03, False, -0.025) for s in roll]) + 100
            last = PL.multi(t0, t1, R, ST, int(np.searchsorted(t0, ts(2025, 10))), ts(2025, 10) + 365 * 86400.0, 20, 0.03, False, -0.025) + 100
            print(f"{nm:10s} q{q} cap{cap}: n{len(sel)} WR {W.mean()*100:.0f}% {R.mean():+.3f}R (невид {R[un].mean():+.3f}R WR {W[un].mean()*100:.0f}%) посл12м WR {W[h].mean()*100:.0f}% {R[h].mean():+.3f}R || посл.12м ${last:,.0f} | год медиана ${np.median(yr):,.0f} хуже-10% ${np.percentile(yr, 10):,.0f} | 6м ниже$100 {np.mean(m6 < 100)*100:.0f}%", flush=True)
