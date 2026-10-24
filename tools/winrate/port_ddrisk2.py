exec(open("port_osc2.py").read().split("sc = rank_score")[0])
xw = X["wt_1d"]
def W_abs(lo, hi, up=1.25, dn=0.85):
    w = base.copy(); ok = (MD == 0) & np.isfinite(xw); f = np.where(xw <= lo, up, np.where(xw >= hi, dn, 1.0)); w[ok] *= f[ok]; return w

@njit
def simd(T0, T1, R, ST, STH, BUF, MD, CID, use, risk, i0, tend, minn, WGT, d1, f1, d2, f2, SHIFT):
    eq = 1.0; peak = 1.0; mdd = 0.0; deps = 1.0; N = 400
    po_t = np.zeros(N); po_r = np.zeros(N); po_m = np.zeros(N); po_u = np.zeros(N); po_c = np.zeros(N, np.int64); po_d = np.zeros(N, np.int64)
    on = np.zeros(N, np.bool_); nmod = np.zeros(4); rmod = np.zeros(4)
    j = i0
    while j < len(T0) and T0[j] < tend:
        if not use[MD[j]]:
            j += 1; continue
        for k in range(N):
            if on[k] and po_t[k] <= T0[j]:
                eq += po_u[k] * (po_r[k] - SHIFT); rmod[po_d[k]] += po_u[k] * (po_r[k] - 0.025); on[k] = False
                if eq > peak: peak = eq
                dd = 1 - eq / peak
                if dd > mdd: mdd = dd
        if eq < 0.1:
            eq = 1.0; peak = 1.0; deps += 1.0
            for k in range(N): on[k] = False
        slot = -1; used = 0.0; ndlm = 0; busy = False
        for k in range(N):
            if on[k]:
                used += po_m[k]
                if po_d[k] == 0: ndlm += 1
                if po_c[k] == CID[j]: busy = True
            elif slot < 0: slot = k
        if slot < 0 or busy or (MD[j] == 0 and ndlm >= 20):
            j += 1; continue
        lev = min(20.0, np.floor(1.0 / (BUF[j] * STH[j] + 0.0105)))
        if lev < 1.0:
            j += 1; continue
        ddn = 1 - eq / peak
        gf = f2 if ddn >= d2 else (f1 if ddn >= d1 else 1.0)
        ru = eq * risk[MD[j]] * WGT[j] * gf; m = ru / ST[j] / lev; free = (eq - used) * 0.9
        if m > free:
            ru = ru * max(free, 0.0) / m; m = max(free, 0.0)
        if ru / ST[j] < minn:
            j += 1; continue
        on[slot] = True; po_t[slot] = T1[j]; po_r[slot] = R[j]; po_m[slot] = m; po_u[slot] = ru; po_c[slot] = CID[j]; po_d[slot] = MD[j]; nmod[MD[j]] += 1
        j += 1
    for k in range(N):
        if on[k]:
            eq += po_u[k] * (po_r[k] - SHIFT); rmod[po_d[k]] += po_u[k] * (po_r[k] - 0.025)
    if eq < 0: eq = 0.0
    return (eq - deps) * 100 + 100, mdd, nmod, rmod * 100

w704 = W_abs(-3, 22); use = np.array([1, 1, 1, 1], np.bool_); rk = np.array([4, 2, 1, 0.5]) / 100
SH = 0.025
def st_dd(nm, d1, f1, d2, f2):
    Y = [simd(T0, T1, R, ST, STH, BUF, MD, CID, use, rk, int(np.searchsorted(T0, s_)), s_ + 365 * 86400.0, 0.05, w704, d1, f1, d2, f2, SH) for s_ in roll2]
    y = np.array([v[0] for v in Y]); dd = np.array([v[1] for v in Y])
    l = simd(T0, T1, R, ST, STH, BUF, MD, CID, use, rk, int(np.searchsorted(T0, ts(2025, 10))), ts(2026, 10), 0.05, w704, d1, f1, d2, f2, SH)
    print(f"{nm:44s} 10% ${np.percentile(y, 10):,.0f} медиана ${np.median(y):,.0f} 90% ${np.percentile(y, 90):,.0f} просадка {np.median(dd)*100:.0f}% (худшая {dd.max()*100:.0f}%) | 12 мес ${l[0]:,.0f}", flush=True)

for sh, lab in ((0.025, "как в бэктесте (−0.025R)"), (0.10, "сделки хуже на 0.10R"), (0.15, "хуже на 0.15R (почти без преимущества)")):
    SH = sh; print("==", lab, flush=True)
    st_dd("риск не зависит от просадки", 9, 1, 9, 1)
    st_dd("≥30% ×1.25, ≥50% ×1.5", 0.3, 1.25, 0.5, 1.5)
    st_dd("≥20% ×1.15, ≥40% ×1.3", 0.2, 1.15, 0.4, 1.3)
    st_dd("≥40% ×1.25, ≥60% ×1.5", 0.4, 1.25, 0.6, 1.5)
