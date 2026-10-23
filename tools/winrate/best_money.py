import os; os.environ["TFH"] = "4"
import numpy as np, warnings; warnings.filterwarnings("ignore")
from numba import njit
exec(open("s25_money.py").read().split("roll = ")[0])
@njit
def sim(t0, t1, R, ST, i0, tend, maxpos, rk, shift):
    """pool.multi with the account's worst drawdown from its peak (by the closes)"""
    eq = 1.0; peak = 1.0; mdd = 0.0; deps = 1.0
    po_t = np.zeros(maxpos); po_r = np.zeros(maxpos); po_m = np.zeros(maxpos); po_u = np.zeros(maxpos); on = np.zeros(maxpos, np.bool_)
    j = i0
    while j < len(t0) and t0[j] < tend:
        for k in range(maxpos):
            if on[k] and po_t[k] <= t0[j]:
                eq += po_u[k] * (po_r[k] + shift); on[k] = False
                if eq > peak: peak = eq
                dd = 1 - eq / peak
                if dd > mdd: mdd = dd
        if eq < 0.1:
            eq = 1.0; peak = 1.0; deps += 1.0
            for k in range(maxpos): on[k] = False
        slot = -1; used = 0.0
        for k in range(maxpos):
            if on[k]: used += po_m[k]
            elif slot < 0: slot = k
        if slot >= 0:
            st = ST[j]; lev = min(20.0, np.floor(1.0 / (1.5 * st + 0.0105)))
            ru = eq * rk; m = ru / st / lev; free = (eq - used) * 0.9
            if m > free:
                if free <= 0.0: ru = 0.0
                else: ru *= free / m; m = free
            if ru > 0:
                on[slot] = True; po_t[slot] = t1[j]; po_r[slot] = R[j]; po_m[slot] = m; po_u[slot] = ru
        j += 1
    for k in range(maxpos):
        if on[k]: eq += po_u[k] * (po_r[k] + shift)
    if eq < 0: eq = 0.0
    return (eq - deps) * 100 + 100, mdd
za = np.load("s25_sc_4h_w1_0_A_base.npz", allow_pickle=True); zb = np.load("s25_sc_4h_w1_0_A_0-1-2-5-8.npz", allow_pickle=True)
ta, tb_ = za["THR"].item(), zb["THR"].item()
SC = (za["SC"] + zb["SC"]) / 2; THR = {Y: (ta[Y] + tb_[Y]) / 2 for Y in ta}
roll = np.arange(ts(2024), ts(2025, 10) + 1, 7 * 86400.0)
rows = []
for q in (0.98, 0.985, 0.99, 0.995):
    for cap in (12, 20, 40):
        sel = select(D, 0, SC, THR, q, cap, ~D["usdc"]); sel = sel[D["t"][sel] >= ts(2022)]
        t0 = D["t"][sel].astype(float); o = np.argsort(t0); sel = sel[o]; t0 = t0[o]
        t1 = t0 + D["K"][0][sel] * 3600.0; R = D["R"][0][sel].astype(float); ST = np.clip(2 * D["F"][sel, 2].astype(float) / 100, 0.002, 0.5)
        for mp in (10, 15, 20, 30):
            for rk in (0.02, 0.03, 0.04, 0.05, 0.06, 0.08):
                res = {}
                for sh, lab in ((-0.025, "c"), (-0.04, "h")):
                    y = np.array([sim(t0, t1, R, ST, int(np.searchsorted(t0, s)), s + 365 * 86400.0, mp, rk, sh) for s in roll])
                    m3 = np.array([sim(t0, t1, R, ST, int(np.searchsorted(t0, s)), s + 91 * 86400.0, mp, rk, sh)[0] for s in roll])
                    res[lab] = (np.median(y[:, 0]), np.percentile(y[:, 0], 10), np.mean(y[:, 0] < 100), np.median(y[:, 1]), np.percentile(y[:, 1], 90), np.mean(m3 < 100))
                rows.append((q, cap, mp, rk, len(sel), res))
                c, h = res["c"], res["h"]
                print(f"q{q} cap{cap:2d} поз{mp:2d} риск{rk*100:.0f}% n{len(sel)} | осторожно: медиана ${c[0]:,.0f} 10% ${c[1]:,.0f} минус {c[2]*100:.0f}% просадка мед {c[3]*100:.0f}% (90%: {c[4]*100:.0f}%) 3м<$100 {c[5]*100:.0f}% | жёстко: ${h[0]:,.0f} 10% ${h[1]:,.0f} просадка 90% {h[4]*100:.0f}%", flush=True)
import pickle; pickle.dump(rows, open("best_money.pkl", "wb"))
