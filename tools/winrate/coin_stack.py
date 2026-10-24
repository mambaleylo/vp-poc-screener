"""the bundle: a second module's signal on a coin already held — skip (now) / take it when the same direction (one-way: adds
to the position) / any (the upper bound). The blocked trades' R by same / opposite direction"""
exec(open("port_expect2.py").read().split("ONE = np.ones")[0])
Bc = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))
DMAP = {}
for p in PC: DMAP[(0, cid(p[5]["sym"]), round(float(p[0])))] = int(p[5]["s"])
for m in ("prv", "smc", "emx"):
    for t in Bc[m]:
        DMAP[(MOD[m], cid(t["s"]), round(float(t.get("f") or t["t"])))] = int(t["d"])
DIR = np.array([DMAP.get((int(MD[i]), int(CID[i]), round(float(T0[i]))), 0) for i in range(len(T0))], np.int64)
print("direction found", np.mean(DIR != 0).round(3), "by module", [np.mean(DIR[MD == k] != 0).round(2) for k in range(4)])
nm = ("⚡", "P/R", "SMC", "EMA"); same = []; opp = []
for i in range(len(T0)):
    on_ = (T0[:i] <= T0[i]) & (T1[:i] > T0[i]) & (CID[:i] == CID[i]) & (MD[:i] != MD[i])
    if on_.any():
        j = np.flatnonzero(on_)[0]; (same if DIR[j] == DIR[i] else opp).append((nm[MD[j]], nm[MD[i]], R[i], R[j]))
for lab, L in (("та же сторона", same), ("встречная", opp)):
    if L: print(f"{lab}: {len(L)} пропущено, их R {np.mean([x[2] for x in L]):+.3f}, WR {np.mean([x[2] > 0 for x in L])*100:.0f}% · R занявшей {np.mean([x[3] for x in L]):+.3f}")
@njit
def sims(T0, T1, R, ST, STH, BUF, MD, CID, DIR, use, risk, i0, tend, minn, WGT, mode):
    eq = 1.0; peak = 1.0; mdd = 0.0; deps = 1.0; N = 400
    po_t = np.zeros(N); po_r = np.zeros(N); po_m = np.zeros(N); po_u = np.zeros(N); po_c = np.zeros(N, np.int64); po_d = np.zeros(N, np.int64); po_s = np.zeros(N, np.int64)
    on = np.zeros(N, np.bool_)
    j = i0
    while j < len(T0) and T0[j] < tend:
        if not use[MD[j]]:
            j += 1; continue
        for k in range(N):
            if on[k] and po_t[k] <= T0[j]:
                eq += po_u[k] * (po_r[k] - 0.025); on[k] = False
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
                if po_c[k] == CID[j]:
                    if mode == 0 or po_d[k] == MD[j]: busy = True
                    elif mode == 1 and po_s[k] != DIR[j]: busy = True
            elif slot < 0: slot = k
        if slot < 0 or busy or (MD[j] == 0 and ndlm >= 20):
            j += 1; continue
        lev = min(20.0, np.floor(1.0 / (BUF[j] * STH[j] + 0.0105)))
        if lev < 1.0:
            j += 1; continue
        ru = eq * risk[MD[j]] * WGT[j]; m = ru / ST[j] / lev; free = (eq - used) * 0.9
        if m > free:
            ru = ru * max(free, 0.0) / m; m = max(free, 0.0)
        if ru / ST[j] < minn:
            j += 1; continue
        on[slot] = True; po_t[slot] = T1[j]; po_r[slot] = R[j]; po_m[slot] = m; po_u[slot] = ru; po_c[slot] = CID[j]; po_d[slot] = MD[j]; po_s[slot] = DIR[j]
        j += 1
    for k in range(N):
        if on[k]: eq += po_u[k] * (po_r[k] - 0.025)
    if eq < 0: eq = 0.0
    return (eq - deps) * 100 + 100, mdd
W = W_of(5, 0.625, 1.25); use = np.array([1, 1, 1, 1], np.bool_); rk = np.array([4, 2, 1, 0.5]) / 100
for mode, lab in ((0, "сейчас: монета занята — пропуск"), (1, "та же сторона — докупка"), (2, "любые (верхняя граница)")):
    Y = [sims(T0, T1, R, ST, STH, BUF, MD, CID, DIR, use, rk, int(np.searchsorted(T0, s_)), s_ + 365 * 86400.0, 0.05, W, mode) for s_ in roll2]
    y = np.array([v[0] for v in Y]); dd = np.array([v[1] for v in Y])
    l = sims(T0, T1, R, ST, STH, BUF, MD, CID, DIR, use, rk, int(np.searchsorted(T0, ts(2025, 10))), ts(2026, 10), 0.05, W, mode)
    print(f"{lab:34s} 10% ${np.percentile(y, 10):,.0f} медиана ${np.median(y):,.0f} 90% ${np.percentile(y, 90):,.0f} просадка {np.median(dd)*100:.0f}% | 12 мес ${l[0]:,.0f}", flush=True)
