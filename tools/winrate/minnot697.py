"""the user: do the money numbers count the trades cut by the margin, "нет маржи" and the skipped ones? sim2 (the bot's
leverage, the liquidation 1.25x) — cut / skipped counted; + Binance's $5 minimum position (a trade under it not opened,
its slot free) from $100; and how many trades a year are cut / skipped"""
exec(open("closetf7.py").read().split("def money3")[0])
@njit
def sim3(t0, t1, R, ST, STH, i0, tend, maxpos, rk, shift, minn):
    eq = 1.0; peak = 1.0; mdd = 0.0; deps = 1.0; ncut = 0; nskip = 0; nfull = 0
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
        if slot < 0:
            nskip += 1; j += 1; continue
        st = ST[j]; lev = min(20.0, np.floor(1.0 / (1.25 * STH[j] + 0.0105)))
        if lev < 1.0:
            nskip += 1; j += 1; continue
        ru = eq * rk; m = ru / st / lev; free = (eq - used) * 0.9; cutf = False
        if m > free:
            if free <= 0.0: ru = 0.0
            else: ru *= free / m; m = free
            cutf = True
        if ru / st < minn:   # under the minimum position (in $100 units): not opened
            nskip += 1; j += 1; continue
        if cutf: ncut += 1
        else: nfull += 1
        on[slot] = True; po_t[slot] = t1[j]; po_r[slot] = R[j]; po_m[slot] = m; po_u[slot] = ru
        j += 1
    for k in range(maxpos):
        if on[k]: eq += po_u[k] * (po_r[k] + shift)
    if eq < 0: eq = 0.0
    return (eq - deps) * 100 + 100, mdd, nfull, ncut, nskip
PC = pool(E, mk2(2.0, 3.0, lambda e: e["tfh"]))
A = np.array([p[:5] for p in PC], float); t0, t1, R, STv, K = A.T; STH = STv * 1.5
for nm, minn in (("как в расчётах (без минимума $5)", 0.0), ("+ минимум позиции $5 на Binance", 0.05)):
    Y = np.array([sim3(t0, t1, R, STv, STH, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.025, minn) for s_ in roll])
    l12 = sim3(t0, t1, R, STv, STH, int(np.searchsorted(t0, ts(2025, 10))), ts(2026, 10), 20, 0.04, -0.025, minn)
    n = Y[:, 2] + Y[:, 3] + Y[:, 4]
    print(f"{nm:34s} медиана ${np.median(Y[:, 0]):,.0f} 10% ${np.percentile(Y[:, 0], 10):,.0f} | 12 мес ${l12[0]:,.0f} | за год сделок {np.median(n):.0f}: "
          f"полных {np.median(Y[:, 2] / n)*100:.0f}%, урезанных {np.median(Y[:, 3] / n)*100:.0f}%, пропущено {np.median(Y[:, 4] / n)*100:.0f}% "
          f"(12 мес: {l12[2]:.0f} / {l12[3]:.0f} / {l12[4]:.0f})", flush=True)
