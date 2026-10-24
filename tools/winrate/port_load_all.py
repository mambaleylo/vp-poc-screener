"""the bundle: the load rule for P/R, SMC, EMA too — each module's own open count at the entry (its pool, as the bot's virtual trades)"""
exec(open("port_expect2.py").read().split("ONE = np.ones")[0])
NOWN = np.zeros(len(T0), np.int64)
for md in (1, 2, 3):
    ix = np.flatnonzero(MD == md)
    for k_, i in enumerate(ix):
        prev = ix[:k_]; NOWN[i] = int(np.sum((T0[prev] <= T0[i]) & (T1[prev] > T0[i])))
for md, nm in ((1, "P/R"), (2, "SMC"), (3, "EMA")):
    ix = MD == md; print(nm, "share open<1", np.mean(NOWN[ix] < 1).round(2), "<2", np.mean(NOWN[ix] < 2).round(2), "<3", np.mean(NOWN[ix] < 3).round(2))
base = W_of(5, 0.625, 1.25)
def W2(rules):
    w = base.copy()
    for md, (n, lo, hi) in rules.items():
        ix = MD == md; w[ix] = np.where(NOWN[ix] < n, lo, hi)
    return w
U = [1, 1, 1, 1]; RK = [4, 2, 1, 0.5]
stats2("связка v703", U, RK, base)
for n in (1, 2, 3):
    for lo, hi in ((0.5, 1.25), (0.625, 1.25), (0.75, 1.25), (0.5, 1.5)):
        stats2(f"все три: <{n} открыто x{lo}, иначе x{hi}", U, RK, W2({1: (n, lo, hi), 2: (n, lo, hi), 3: (n, lo, hi)}))
for md, nm in ((1, "P/R"), (2, "SMC"), (3, "EMA")):
    for n in (1, 3):
        stats2(f"только {nm}: <{n} x0.625, иначе x1.25", U, RK, W2({md: (n, 0.625, 1.25)}))
