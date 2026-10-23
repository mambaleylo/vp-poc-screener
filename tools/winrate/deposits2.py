"""⚡ 4h, 20 positions x 4%: start $100 + a monthly top-up (none / $25 / $50 / $100) vs the same money at once; 6 / 12
months, starts weekly over 2024–26, cautious (-0.025R a trade) and harsh (-0.04R)"""
import os; os.environ["TFH"] = "4"
import numpy as np, warnings; warnings.filterwarnings("ignore")
from numba import njit
exec(open("best_money.py").read().split("za = np.load")[0])
POOL, RK = os.environ["POOL"], float(os.environ["RK"])
@njit
def simd(t0, t1, R, ST, i0, tend, maxpos, rk, shift, start, dep):
    eq = start; nxt = t0[i0] + 30.4 * 86400 if i0 < len(t0) else tend; put = start; peak = eq; mdd = 0.0
    po_t = np.zeros(maxpos); po_r = np.zeros(maxpos); po_m = np.zeros(maxpos); po_u = np.zeros(maxpos); on = np.zeros(maxpos, np.bool_)
    j = i0
    while j < len(t0) and t0[j] < tend:
        while t0[j] >= nxt and nxt < tend:
            eq += dep; put += dep; nxt += 30.4 * 86400
        for k in range(maxpos):
            if on[k] and po_t[k] <= t0[j]:
                eq += po_u[k] * (po_r[k] + shift); on[k] = False
        if eq > peak: peak = eq
        if peak > 0 and 1 - eq / peak > mdd: mdd = 1 - eq / peak
        if eq < 1.0:
            for k in range(maxpos): on[k] = False
        slot = -1; used = 0.0
        for k in range(maxpos):
            if on[k]: used += po_m[k]
            elif slot < 0: slot = k
        if slot >= 0 and eq >= 1.0:
            st = ST[j]; lev = min(20.0, np.floor(1.0 / (1.5 * st + 0.0105)))
            ru = eq * rk; m = ru / st / lev; free = (eq - used) * 0.9
            if m > free:
                if free <= 0.0: ru = 0.0
                else: ru *= free / m; m = free
            if ru > 0:
                on[slot] = True; po_t[slot] = t1[j]; po_r[slot] = R[j]; po_m[slot] = m; po_u[slot] = ru
        j += 1
    while nxt < tend:
        eq += dep; put += dep; nxt += 30.4 * 86400
    for k in range(maxpos):
        if on[k]: eq += po_u[k] * (po_r[k] + shift)
    return eq, put, mdd
P = np.load(POOL)   # the pool order: time, then the higher score — never by the exit time
t0, t1, R, STv = P[:, 0], P[:, 1], P[:, 2], P[:, 3]
for mo in (6, 12):
    starts = np.arange(ts(2024), ts(2026, 10) - mo * 30.4 * 86400, 7 * 86400.0)
    for start, dep, nm in ((100, 0, "$100, без пополнений"), (100, 25, "$100 + $25/мес"), (100, 50, "$100 + $50/мес"), (100, 100, "$100 + $100/мес"),
                           (100 + 50 * mo, 0, f"${100 + 50 * mo} сразу (как +$50/мес)")):
        for sh, lab in ((-0.025, "осторожно"), (-0.04, "жёстко")):
            o = np.array([simd(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + mo * 30.4 * 86400, 20, RK, sh, float(start), float(dep)) for s_ in starts])
            eq, put, dd = o[:, 0], o[:, 1], o[:, 2]
            print(f"{mo:2d} мес {nm:28s} {lab:9s}: вложено ${put[0]:,.0f} · на счёте медиана ${np.median(eq):,.0f} · худшие 10% ${np.percentile(eq, 10):,.0f} · меньше вложенного {np.mean(eq < put) * 100:.0f}% · просадка мед {np.median(dd) * 100:.0f}%", flush=True)
