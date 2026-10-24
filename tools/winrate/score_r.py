"""⚡: does a trade's R grow with the model's score (relative to the year's threshold)? the deployed pool (v0.99.695 exits)"""
exec(open("closetf7.py").read().split("def money3")[0])
P = pool(E, mk2(2.0, 3.0, lambda e: e["tfh"]))
sc = np.array([-p[5]["key"][2] for p in P]); R = np.array([p[2] for p in P]); t0 = np.array([p[0] for p in P])
yr = (t0.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970)
# the score relative to the stream's yearly threshold is not stored: use its rank within the stream & year as the bucket (descriptive only)
tfh = np.array([p[5]["tfh"] for p in P])
for tf in (4, 2):
    for Y in range(2023, 2027):
        m = (tfh == tf) & (yr == Y)
        if m.sum() < 40: continue
        q = np.quantile(sc[m], [0.5, 0.8])
        lo, mid, hi = m & (sc < q[0]), m & (sc >= q[0]) & (sc < q[1]), m & (sc >= q[1])
        print(f"{tf}ч {Y}: нижняя половина {R[lo].mean():+.3f}R ({lo.sum()}) · 50–80% {R[mid].mean():+.3f}R ({mid.sum()}) · верхние 20% {R[hi].mean():+.3f}R ({hi.sum()})", flush=True)
# the causal weight: the 4h stream's score above the previous year's median of its pool trades -> x hi, else x lo; 2h x1
med = {}
for Y in range(2022, 2027):
    m = (tfh == 4) & (yr == Y - 1)
    med[Y] = float(np.median(sc[m])) if m.sum() > 30 else np.inf
W_hi = np.array([sc[i] >= med[yr[i]] if tfh[i] == 4 else False for i in range(len(P))])
W_lo = np.array([(sc[i] < med[yr[i]]) if tfh[i] == 4 else False for i in range(len(P))])
@njit
def sim_w(t0, t1, R, ST, STH, W, i0, tend, maxpos, rk, shift):
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
            st = ST[j]; lev = min(20.0, np.floor(1.0 / (1.25 * STH[j] + 0.0105)))
            if lev >= 1.0:
                ru = eq * rk * W[j]; m = ru / st / lev; free = (eq - used) * 0.9
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
A = np.array([p[:5] for p in P], float); T0_, T1_, R_, ST_, K_ = A.T; STH_ = ST_ * 1.5
o = np.argsort(T0_, kind="stable"); T0_, T1_, R_, ST_, STH_ = T0_[o], T1_[o], R_[o], ST_[o], STH_[o]; Wh, Wl = W_hi[o], W_lo[o]
for hi, lo in ((1.0, 1.0), (1.3, 0.7), (1.5, 0.5), (1.2, 1.0), (1.0, 0.7)):
    W = np.where(Wh, hi, np.where(Wl, lo, 1.0))
    y = np.array([sim_w(T0_, T1_, R_, ST_, STH_, W, int(np.searchsorted(T0_, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.025) for s_ in roll])
    l12 = sim_w(T0_, T1_, R_, ST_, STH_, W, int(np.searchsorted(T0_, ts(2025, 10))), ts(2026, 10), 20, 0.04, -0.025)
    print(f"4ч выше медианы x{hi}, ниже x{lo}: медиана ${np.median(y[:, 0]):,.0f} 10% ${np.percentile(y[:, 0], 10):,.0f} просадка {np.median(y[:, 1])*100:.0f}% | 12 мес ${l12[0]:,.0f}", flush=True)
