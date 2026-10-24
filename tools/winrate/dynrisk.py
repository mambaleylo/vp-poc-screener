"""⚡: the risk by how busy the account is (causal — the open positions at the entry): more when few are open (a quiet
market, the margin free), less in a bunch (the bunches go one way and stop together). The deployed pool, the bot's leverage"""
exec(open("closetf7.py").read().split("def money3")[0])
P = pool(E, mk2(2.0, 3.0, lambda e: e["tfh"]))
A = np.array([p[:5] for p in P], float); T0_, T1_, R_, ST_, K_ = A.T; STH_ = ST_ * 1.5
SD = np.array([p[5]["s"] for p in P], np.int64)
@njit
def sim_d(t0, t1, R, ST, STH, SD, i0, tend, maxpos, levels, risks, side_mode, shift):
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
            st = ST[j]; lev = min(20.0, np.floor(1.0 / (1.25 * STH[j] + 0.0105)))
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
def run(nm, levels, risks, side_mode=False):
    lv = np.array(levels, np.int64); rk = np.array(risks, float) / 100
    y = np.array([sim_d(T0_, T1_, R_, ST_, STH_, SD, int(np.searchsorted(T0_, s_)), s_ + 365 * 86400.0, 20, lv, rk, side_mode, -0.025) for s_ in roll])
    l12 = sim_d(T0_, T1_, R_, ST_, STH_, SD, int(np.searchsorted(T0_, ts(2025, 10))), ts(2026, 10), 20, lv, rk, side_mode, -0.025)
    print(f"{nm:44s} медиана ${np.median(y[:, 0]):>6,.0f} 10% ${np.percentile(y[:, 0], 10):>5,.0f} просадка {np.median(y[:, 1])*100:.0f}% | 12 мес ${l12[0]:,.0f}", flush=True)
run("всегда 4% (сейчас)", [99], [4])
run("открыто <3: 6%, <8: 4%, дальше 3%", [3, 8], [6, 4, 3])
run("открыто <3: 6%, <8: 4%, дальше 2%", [3, 8], [6, 4, 2])
run("открыто <5: 5%, <10: 4%, дальше 2%", [5, 10], [5, 4, 2])
run("открыто <3: 8%, <6: 5%, дальше 3%", [3, 6], [8, 5, 3])
run("в ту же сторону <3: 6%, <8: 4%, дальше 2%", [3, 8], [6, 4, 2], True)
run("в ту же сторону <5: 5%, дальше 3%", [5], [5, 3], True)
