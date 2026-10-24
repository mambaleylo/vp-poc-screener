"""⚡ risk by the daily oscillators (GitHub: WaveTrend LazyBear, Ehlers Fisher, EWO) x the side at the entry: stretched
against the trade -> more. Causal: the score's cut-offs = the quantiles of the ⚡ trades of the years BEFORE (expanding)"""
exec(open("port_expect2.py").read().split("ONE = np.ones")[0])
G = [r for r in json.load(open("gh_dlm.json"))]
assert len(G) == len(PC)
key = {}
for p, r in zip(PC, G):
    if r: key[(cid(p[5]["sym"]), round(float(p[0])))] = r
def col(k):
    return np.array([key.get((int(CID[i]), round(float(T0[i]))), {}).get(k, np.nan) if MD[i] == 0 else np.nan for i in range(len(T0))])
X = {k: col(k) for k in ("wt_1d", "fisher_1d", "ewo_1d")}
YR = (T0.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970)
def rank_score(names):
    # each oscillator -> its percentile vs the ⚡ trades of the earlier years; the score = the mean percentile
    sc = np.full(len(T0), np.nan)
    for Y in range(2023, 2027):
        cur = (MD == 0) & (YR == Y); past = (MD == 0) & (YR < Y)
        ps = []
        for k in names:
            ref = np.sort(X[k][past & np.isfinite(X[k])])
            ps.append(np.searchsorted(ref, X[k][cur]) / max(len(ref), 1))
        sc[cur] = np.mean(ps, 0)
    return sc
base = W_of(5, 0.625, 1.25)
def W_osc(sc, lo_q, hi_q, up, dn):
    w = base.copy(); ok = (MD == 0) & np.isfinite(sc)
    f = np.where(sc <= lo_q, up, np.where(sc >= hi_q, dn, 1.0)); w[ok] *= f[ok]; return w
for nm, names in (("wt", ["wt_1d"]), ("три", ["wt_1d", "fisher_1d", "ewo_1d"])):
    sc = rank_score(names)
    ix = (MD == 0) & np.isfinite(sc)
    for Y in range(2023, 2027):
        m = ix & (YR == Y); print(nm, Y, "низ 40%", R[m & (sc <= 0.4)].mean().round(3), "верх 40%", R[m & (sc >= 0.6)].mean().round(3), m.sum())
    for up, dn in ((1.3, 0.7), (1.5, 0.5), (1.25, 0.85)):
        stats2(f"⚡ {nm}: против ×{up}, по ходу ×{dn}", [1, 0, 0, 0], [4, 0, 0, 0], W_osc(sc, 0.4, 0.6, up, dn))
        stats2(f"связка, ⚡ {nm}: ×{up}/×{dn}", [1, 1, 1, 1], [4, 2, 1, 0.5], W_osc(sc, 0.4, 0.6, up, dn))
stats2("⚡ v703", [1, 0, 0, 0], [4, 0, 0, 0], base)
stats2("связка v703", [1, 1, 1, 1], [4, 2, 1, 0.5], base)
