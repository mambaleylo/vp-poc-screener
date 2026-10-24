"""dynrisk4: the risk by the count of ALL ⚡ trades open at the entry (the bot can count its virtual + real ones = the pool)"""
"""⚡: the risk by how busy the account is (causal — the open positions at the entry): more when few are open (a quiet
market, the margin free), less in a bunch (the bunches go one way and stop together). The deployed pool, the bot's leverage"""
exec(open("closetf7.py").read().split("def money3")[0])
P = pool(E, mk2(2.0, 3.0, lambda e: e["tfh"]))
A = np.array([p[:5] for p in P], float); T0_, T1_, R_, ST_, K_ = A.T; STH_ = ST_ * 1.5
SD = np.array([p[5]["s"] for p in P], np.int64)
@njit
def sim_d(t0, t1, R, ST, STH, SD, i0, tend, maxpos, levels, risks, side_mode, shift, LEVCAP=20.0):
    eq = 1.0; peak = 1.0; mdd = 0.0; deps = 1.0
    po_t = np.zeros(maxpos); po_r = np.zeros(maxpos); po_m = np.zeros(maxpos); po_u = np.zeros(maxpos); po_s = np.zeros(maxpos); on = np.zeros(maxpos, np.bool_)
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
        slot = -1; used = 0.0; n_open = 0; n_side = 0
        for k in range(maxpos):
            if on[k]:
                used += po_m[k]; n_open += 1
                if po_s[k] == SD[j]: n_side += 1
            elif slot < 0: slot = k
        if slot >= 0:
            cnt = n_side if side_mode else n_open
            rk = risks[len(risks) - 1]
            for q in range(len(levels)):
                if cnt < levels[q]:
                    rk = risks[q]; break
            st = ST[j]; lev = min(LEVCAP, np.floor(1.0 / (1.25 * STH[j] + 0.0105)))
            if lev >= 1.0:
                ru = eq * rk; m = ru / st / lev; free = (eq - used) * 0.9
                if m > free:
                    if free <= 0.0: ru = 0.0
                    else: ru *= free / m; m = free
                if ru > 0:
                    on[slot] = True; po_t[slot] = t1[j]; po_r[slot] = R[j]; po_m[slot] = m; po_u[slot] = ru; po_s[slot] = SD[j]
        j += 1
    for k in range(maxpos):
        if on[k]: eq += po_u[k] * (po_r[k] + shift)
    if eq < 0: eq = 0.0
    return (eq - deps) * 100 + 100, mdd
@njit
def sim_w(t0, t1, R, ST, STH, W, i0, tend, maxpos, rk, shift, LEVCAP=20.0):
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
            st = ST[j]; lev = min(LEVCAP, np.floor(1.0 / (1.25 * STH[j] + 0.0105)))
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
# the count the bot has: all ⚡ trades open at the entry (virtual + real) = the pool's own
o = np.argsort(T0_, kind="stable"); T0_, T1_, R_, ST_, STH_, SD = T0_[o], T1_[o], R_[o], ST_[o], STH_[o], SD[o]
NOPEN = np.zeros(len(T0_), np.int64)
for i in range(len(T0_)):
    NOPEN[i] = int(np.sum((T0_[:i] <= T0_[i]) & (T1_[:i] > T0_[i])))
def run2(nm, levels, risks):
    lv = np.array(levels); rk = np.array(risks, float) / 100
    W = np.array([rk[int(np.searchsorted(lv, n, side="right"))] for n in NOPEN])   # the risk of each trade by the pool's count
    W = W / 0.04
    exec_ = sim_w
    y = np.array([exec_(T0_, T1_, R_, ST_, STH_, W, int(np.searchsorted(T0_, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.025) for s_ in roll])
    l12 = exec_(T0_, T1_, R_, ST_, STH_, W, int(np.searchsorted(T0_, ts(2025, 10))), ts(2026, 10), 20, 0.04, -0.025)
    by = []
    for Y in (2024, 2025):
        yy = np.array([exec_(T0_, T1_, R_, ST_, STH_, W, int(np.searchsorted(T0_, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.025)[0] for s_ in roll if ts(Y) <= s_ < ts(Y + 1)])
        by.append(f"{Y}: ${np.median(yy):,.0f}")
    print(f"{nm:40s} медиана ${np.median(y[:, 0]):>6,.0f} 10% ${np.percentile(y[:, 0], 10):>5,.0f} просадка {np.median(y[:, 1])*100:.0f}% | 12 мес ${l12[0]:,.0f} | старт в {' · '.join(by)}", flush=True)


W = np.where(NOPEN < 5, 0.625, 1.25)
def runP(nm, mp, lc, rk=0.04):
    y = np.array([sim_w(T0_, T1_, R_, ST_, STH_, W, int(np.searchsorted(T0_, s_)), s_ + 365 * 86400.0, mp, rk, -0.025, lc) for s_ in roll])
    l12 = sim_w(T0_, T1_, R_, ST_, STH_, W, int(np.searchsorted(T0_, ts(2025, 10))), ts(2026, 10), mp, rk, -0.025, lc)
    print(f"{nm:34s} медиана ${np.median(y[:, 0]):>6,.0f} 10% ${np.percentile(y[:, 0], 10):>5,.0f} 90% ${np.percentile(y[:, 0], 90):>6,.0f} просадка {np.median(y[:, 1])*100:.0f}% | 12 мес ${l12[0]:,.0f}", flush=True)
for mp in (10, 15, 20, 25, 30, 40):
    runP(f"позиций {mp}, плечо до 20", mp, 20.0)
for lc in (10.0, 30.0, 50.0):
    runP(f"позиций 20, плечо до {lc:.0f}", 20, lc)
for rk in (0.03, 0.05):
    runP(f"позиций 20, риск {rk*100:.0f}%", 20, 20.0, rk)
