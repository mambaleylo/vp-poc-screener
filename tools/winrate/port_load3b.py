"""the ⚡ load rule for P/R / SMC / EMA: the module's own open trades at the entry < n -> risk x lo, else x hi (the
v0.99.712 rules for ⚡ kept); per module, then together"""
exec(open("port_w712.py").read().split("U = [1, 1, 1, 1]")[0])
rebuild("smcqx_0.993_3.0_96_1.0_2.0_4.npy", "emaqr_0.96_1.5_4.npy")
NOm = np.zeros(len(T0), np.int64)
for m_ in (1, 2, 3):
    idx = np.flatnonzero(MD == m_)
    for k_, i in enumerate(idx):
        prev = idx[:k_]; NOm[i] = int(np.sum((T0[prev] <= T0[i]) & (T1[prev] > T0[i])))
WB = W_abs(-3, 22)
def wl(spec):
    w = WB.copy()
    for m_, (n, lo, hi) in spec.items():
        sel = MD == m_; w[sel] *= np.where(NOm[sel] < n, lo, hi)
    return w

def wn(spec):   # the same, normalised: the module's mean multiplier = 1 (only the split moves, not the average risk)
    w = WB.copy()
    for m_, (n, lo, hi) in spec.items():
        sel = MD == m_; f = np.where(NOm[sel] < n, lo, hi); w[sel] *= f / f.mean()
    return w
U = [1, 1, 1, 1]; RK = [4, 2, 1.5, 1]
for m_ in (1, 2, 3):
    sel = MD == m_; print("module", m_, "share with fewer than 2 open", round(float(np.mean(NOm[sel] < 2)), 2))
stats2("сейчас", U, RK, WB)
S3 = {1: (2, 0.5, 1.4), 2: (2, 0.5, 1.4), 3: (1, 0.5, 1.4)}
stats2("все три x0.5 / x1.4 (как было)", U, RK, wl(S3))
stats2("все три x0.5 / x1.4, средний риск тот же", U, RK, wn(S3))
f = {m_: float(np.where(NOm[MD == m_] < S3[m_][0], 0.5, 1.4).mean()) for m_ in (1, 2, 3)}
print("mean multipliers", {k: round(v, 2) for k, v in f.items()})
stats2(f"просто риск x средний множитель (P/R {2*f[1]:.2f}, SMC {1.5*f[2]:.2f}, EMA {f[3]:.2f})", U, [4, 2 * f[1], 1.5 * f[2], f[3]], WB)
print("fin")
