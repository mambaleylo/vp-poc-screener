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
U = [1, 1, 1, 1]; RK = [4, 2, 1.5, 1]
stats2("сейчас", U, RK, WB)
for nm, spec in (("P/R <2: x0.6, иначе x1.2", {1: (2, 0.6, 1.2)}), ("P/R <2: x0.5, иначе x1.4", {1: (2, 0.5, 1.4)}), ("P/R <4: x0.7, иначе x1.3", {1: (4, 0.7, 1.3)}),
                 ("SMC <2: x0.6, иначе x1.2", {2: (2, 0.6, 1.2)}), ("SMC <2: x0.5, иначе x1.4", {2: (2, 0.5, 1.4)}),
                 ("EMA <1: x0.6, иначе x1.2", {3: (1, 0.6, 1.2)}), ("EMA <2: x0.6, иначе x1.2", {3: (2, 0.6, 1.2)}),
                 ("все три (P/R<2, SMC<2, EMA<1: x0.6 / x1.2)", {1: (2, 0.6, 1.2), 2: (2, 0.6, 1.2), 3: (1, 0.6, 1.2)}),
                 ("все три x0.5 / x1.4", {1: (2, 0.5, 1.4), 2: (2, 0.5, 1.4), 3: (1, 0.5, 1.4)})):
    stats2(nm, U, RK, wl(spec))
print("fin")
