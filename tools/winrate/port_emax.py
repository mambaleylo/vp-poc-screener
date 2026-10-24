"""the bundle with SMC at q 0.99 (deployed) / 0.993 / 0.995 and its risk, the v0.99.704 ⚡ rules"""
exec(open("port_osc3.py").read().split('print("медиана wt')[0])
def rebuild(f, fe="ema_cs_1.5_4.npy"):
    global NO, base, X, xw
    setrows(build(f, fe))
    NO = np.zeros(len(T0), np.int64); dl = np.flatnonzero(MD == 0)
    for k_, i in enumerate(dl):
        prev = dl[:k_]; NO[i] = int(np.sum((T0[prev] <= T0[i]) & (T1[prev] > T0[i])))
    base = W_of(5, 0.625, 1.25); X = {k: col(k) for k in ("wt_1d",)}; xw = X["wt_1d"]
U = [1, 1, 1, 1]
for fe, nm in (("emaqx_4.0_72.npy", "EMA 72ч (сейчас)"), ("emaqx_4.0_96.npy", "EMA 96ч"), ("emaqx_4.0_120.npy", "EMA 120ч")):
    rebuild("smcqx_0.993_3.0_96_1.0_2.0_4.npy", fe)
    stats2(nm, U, [4, 2, 1.5, 0.5], W_abs(-3, 22))
