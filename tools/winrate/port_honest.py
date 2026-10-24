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
rebuild("smcqr_0.993_1.0_2.0_4.npy"); stats2("SMC честный, EMA старый список", U, [4, 2, 1.5, 0.5], W_abs(-3, 22))
rebuild("smcqr_0.993_1.0_2.0_4.npy", "emaqr_0.96_1.5_4.npy")
for rk in ([4, 2, 1.5, 0.5], [4, 2, 1.5, 1], [4, 2, 1.5, 2]):
    stats2(f"оба честных, ⚡{rk[0]} P/R{rk[1]} SMC{rk[2]} EMA{rk[3]}", U, rk, W_abs(-3, 22))
