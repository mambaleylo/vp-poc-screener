"""the bundle: SMC / EMA risk by the SSL trend (GitHub: SSL channel) at the entry — with it x hi, against x lo (mean ~1)"""
exec(open("port_expect2.py").read().split("ONE = np.ones")[0])
G = json.load(open("gh_states.json"))
GM = {(MOD[r["mod"]], cid(r["s"]), round(r["te"])): r for r in G}
def feat(k):
    return np.array([GM.get((int(MD[i]), int(CID[i]), round(float(T0[i]))), {}).get(k, np.nan) for i in range(len(T0))])
S1d, S4h = feat("ssl_1d"), feat("ssl_4h")
for md, nm in ((2, "SMC"), (3, "EMA")):
    ix = MD == md; print(nm, "найдено", np.isfinite(S1d[ix]).mean().round(2), "против 1d", np.mean(S1d[ix] < 0).round(2), "против 4h", np.mean(S4h[ix] < 0).round(2))
base = W_of(5, 0.625, 1.25); U = [1, 1, 1, 1]; RK = [4, 2, 1, 0.5]
def rw(md, x, lo, hi):
    w = base.copy(); ix = (MD == md) & np.isfinite(x); w[ix] = np.where(x[ix] < 0, lo, hi); return w
stats2("связка v703", U, RK, base)
for lo, hi in ((0.5, 1.15), (0.0, 1.0), (0.5, 1.0)):
    stats2(f"SMC: SSL 1d против x{lo}, с ним x{hi}", U, RK, rw(2, S1d, lo, hi))
    stats2(f"EMA: SSL 4h против x{lo}, с ним x{hi}", U, RK, rw(3, S4h, lo, hi))
w = rw(2, S1d, 0.5, 1.15); ix = (MD == 3) & np.isfinite(S4h); w[ix] = np.where(S4h[ix] < 0, 0.5, 1.3)
stats2("оба: SMC 1d 0.5/1.15, EMA 4h 0.5/1.3", U, RK, w)
