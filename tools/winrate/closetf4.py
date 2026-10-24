"""closetf3 with the bot's leverage: the bot sizes the position at the 2 ATR stop (the risk %), but its leverage keeps the
liquidation beyond the EMERGENCY stop (compute_risk_based_position at the hard stop) — the money sim had the leverage by
the 2 ATR stop (fine for a touch stop; a farther emergency stop looked free). sim2: the margin by the hard stop"""
exec(open("closetf2.py").read().split("P1 = pool(")[0])
@njit
def sim2(t0, t1, R, ST, STH, i0, tend, maxpos, rk, shift):
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
            st = ST[j]; lev = min(20.0, np.floor(1.0 / (1.5 * STH[j] + 0.0105)))
            if lev < 1.0:   # the bot: no safe leverage at the emergency stop -> skipped
                j += 1
                continue
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
def money2(nm, P, hard, rk=0.04, ref=None):
    A = np.array([p[:5] for p in P], float); t0, t1, R, STv, K = A.T; STH = STv * hard / 2.0
    y = np.array([sim2(t0, t1, R, STv, STH, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, rk, -0.025) for s_ in roll])
    yh = np.array([sim2(t0, t1, R, STv, STH, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, rk, -0.04)[0] for s_ in roll])
    l12 = sim2(t0, t1, R, STv, STH, int(np.searchsorted(t0, ts(2025, 10))), ts(2026, 10), 20, rk, -0.025)
    m6 = np.array([sim2(t0, t1, R, STv, STH, int(np.searchsorted(t0, s_)), s_ + 182 * 86400.0, 20, rk, -0.025)[0] for s_ in roll])
    extra = "" if ref is None else f" | окон лучше: {np.mean(y[:, 0] > ref)*100:.0f}%, x{np.median(y[:, 0] / ref):.2f}"
    print(f"{nm:34s} WR {np.mean(K == 1)*100:.0f}% {R.mean():+.3f}R авар {np.mean(K == 0)*100:.1f}% | медиана ${np.median(y[:, 0]):>6,.0f} 10% ${np.percentile(y[:, 0], 10):>5,.0f} "
          f"просадка {np.median(y[:, 1])*100:.0f}% жёстко ${np.median(yh):,.0f} | с 10.2025 ${l12[0]:,.0f} | 6 мес <$100 {np.mean(m6 < 100)*100:.0f}%{extra}", flush=True)
    return y[:, 0]
r0 = money2("сейчас: закр. 1ч, авар. 3", pool(E, mk2(2.0, 3.0, lambda e: 1)), 3.0)
for hard in (3.0, 3.25, 3.5, 4.0):
    money2(f"закр. свечи графика, авар. {hard}", pool(E, mk2(2.0, hard, lambda e: e["tfh"])), hard, ref=r0)
money2("закр. 4ч всем, авар. 3", pool(E, mk2(2.0, 3.0, lambda e: 4)), 3.0, ref=r0)
print("== риск, закр. свечи графика")
for hard in (3.0, 3.5):
    P = pool(E, mk2(2.0, hard, lambda e: e["tfh"]))
    for r in (0.03, 0.05, 0.06): money2(f"авар. {hard}, риск {r*100:.0f}%", P, hard, rk=r, ref=r0)
