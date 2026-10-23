"""lab after v0.99.689: the risk by the account's drawdown (the deployed 4h + 2h pool, pool689.npy) — at a drawdown
beyond d from the peak the risk a trade is x times the base; plus the positions / risk grid. 12-month windows started
weekly over 2024–26 from $100, cautious −0.025R / harsh −0.04R"""
import numpy as np
from numba import njit
from mk import ts
@njit
def sim(t0, t1, R, ST, i0, tend, maxpos, rk, shift, d1, x1, d2, x2):
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
            ddn = 1 - eq / peak; r_ = rk
            if ddn > d2: r_ = rk * x2
            elif ddn > d1: r_ = rk * x1
            st = ST[j]; lev = min(20.0, np.floor(1.0 / (1.5 * st + 0.0105)))
            ru = eq * r_; m = ru / st / lev; free = (eq - used) * 0.9
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
P = np.load("pool689.npy"); P = P[np.argsort(P[:, 0], kind="stable")]
t0, t1, R, ST = P[:, 0].copy(), P[:, 1].copy(), P[:, 2].copy(), P[:, 3].copy()
roll = np.arange(ts(2024), ts(2025, 10) + 1, 7 * 86400.0)
def run(nm, mp, rk, d1=9, x1=1, d2=9, x2=1):
    y = np.array([sim(t0, t1, R, ST, int(np.searchsorted(t0, s)), s + 365 * 86400.0, mp, rk, -0.025, d1, x1, d2, x2) for s in roll])
    yh = np.array([sim(t0, t1, R, ST, int(np.searchsorted(t0, s)), s + 365 * 86400.0, mp, rk, -0.04, d1, x1, d2, x2)[0] for s in roll])
    print(f"{nm:44s} медиана ${np.median(y[:, 0]):>7,.0f} 10% ${np.percentile(y[:, 0], 10):>6,.0f} хуже всех ${y[:, 0].min():>6,.0f} | "
          f"просадка {np.median(y[:, 1])*100:.0f}%/{np.percentile(y[:, 1], 90)*100:.0f}%/макс {y[:, 1].max()*100:.0f}% | жёстко ${np.median(yh):,.0f}", flush=True)
print("== позиций × риск")
for mp in (15, 20, 25, 30):
    for rk in (0.03, 0.04, 0.05):
        run(f"{mp} позиций, {rk*100:.0f}%", mp, rk)
print("== риск по просадке (20 позиций, база 4% / 5%)")
for rk in (0.04, 0.05):
    for d1, x1, d2, x2 in ((0.2, 0.75, 0.4, 0.5), (0.25, 0.5, 9, 1), (0.3, 0.5, 0.5, 0.25), (0.15, 0.75, 0.3, 0.5), (0.35, 0.5, 9, 1), (0.2, 0.5, 0.4, 0.25)):
        run(f"{rk*100:.0f}%, просадка>{d1*100:.0f}% ×{x1}, >{d2*100:.0f}% ×{x2}" if d2 < 1 else f"{rk*100:.0f}%, просадка>{d1*100:.0f}% ×{x1}", 20, rk, d1, x1, d2, x2)
