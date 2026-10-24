"""the bundle with SMC at q 0.99 (deployed) / 0.993 / 0.995 and its risk, the v0.99.704 ⚡ rules"""
exec(open("port_osc3.py").read().split('print("медиана wt')[0])
def rebuild(f):
    global NO, base, X, xw
    setrows(build(f, "ema_cs_1.5_4.npy"))
    NO = np.zeros(len(T0), np.int64); dl = np.flatnonzero(MD == 0)
    for k_, i in enumerate(dl):
        prev = dl[:k_]; NO[i] = int(np.sum((T0[prev] <= T0[i]) & (T1[prev] > T0[i])))
    base = W_of(5, 0.625, 1.25); X = {k: col(k) for k in ("wt_1d",)}; xw = X["wt_1d"]
U = [1, 1, 1, 1]
for q in (0.99, 0.993, 0.995):
    rebuild(f"smcq_{q}_1.0_2.0_4.npy")
    for rs in ((1.0,) if q == 0.99 else (1.0, 1.5, 2.0)):
        stats2(f"SMC q{q} риск {rs}%", U, [4, 2, rs, 0.5], W_abs(-3, 22))
