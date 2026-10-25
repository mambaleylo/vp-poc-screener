"""the margin binds (the user: "ты прав про то, что надолго маржу задерживает"): isolated margin with the leverage by the
liquidation buffer (now) vs a fixed leverage (cross margin: the positions share the balance, the exchange stops protect;
the initial margin = notional / L). How often the free margin cuts / skips a trade; the money; the account's worst moment
(the sum of the open trades' losses if all hit their emergency stops at once, in % of the equity)"""
exec(open("port_w712.py").read().split("U = [1, 1, 1, 1]")[0])
rebuild("smcqx_0.993_3.0_96_1.0_2.0_4.npy", "emaqr_0.96_1.5_4.npy")
src = open("port_expect2.py").read(); src = "@njit\ndef simp" + src.split("@njit\ndef simp")[1].split("\nroll2")[0]
src = src.replace("def simp(T0, T1, R, ST, STH, BUF, MD, CID, use, risk, i0, tend, minn, WGT):", "def simx(T0, T1, R, ST, STH, BUF, MD, CID, use, risk, i0, tend, minn, WGT, LEVF, LCAP):")
src = src.replace("lev = min(20.0, np.floor(1.0 / (BUF[j] * STH[j] + 0.0105)))", "lev = LEVF if LEVF > 0 else min(LCAP, np.floor(1.0 / (BUF[j] * STH[j] + 0.0105)))")
src = src.replace("eq = 1.0; peak = 1.0; mdd = 0.0; deps = 1.0; N = 400", "eq = 1.0; peak = 1.0; mdd = 0.0; deps = 1.0; N = 400; ncut = 0; nskip = 0; ntot = 0; worst = 0.0")
src = src.replace("        if m > free:\n            ru = ru * max(free, 0.0) / m; m = max(free, 0.0)",
                  "        ntot += 1\n        if m > free:\n            ncut += 1\n            ru = ru * max(free, 0.0) / m; m = max(free, 0.0)")
src = src.replace("        if ru / ST[j] < minn:\n            j += 1; continue", "        if ru / ST[j] < minn:\n            nskip += 1\n            j += 1; continue")
# the worst moment: the open trades' loss at their emergency stops / the equity, after each new trade
src = src.replace("po_d[slot] = MD[j]; nmod[MD[j]] += 1", "po_d[slot] = MD[j]; nmod[MD[j]] += 1\n        hl = 0.0\n        for k in range(N):\n            if on[k]: hl += po_u[k] * STH[j] / ST[j] if k == slot else po_u[k] * 1.5\n        if hl / eq > worst: worst = hl / eq")
src = src.replace("return (eq - deps) * 100 + 100, mdd, nmod, rmod * 100", "return (eq - deps) * 100 + 100, mdd, nmod, rmod * 100, ncut, nskip, ntot, worst")
assert "ncut += 1" in src and "nskip += 1" in src and "LEVF > 0" in src and "worst = hl / eq" in src
exec(src)
WB = W_abs(-3, 22)
def st(nm, levf=0.0, lcap=20.0, use=(1, 1, 1, 1), rk=(4, 2, 1.5, 1)):
    use = np.array(use, np.bool_); rk = np.array(rk, float) / 100
    f = lambda a, b: simx(T0, T1, R, ST, STH, BUF, MD, CID, use, rk, int(np.searchsorted(T0, a)), b, 0.05, WB, float(levf), float(lcap))
    Y = [f(s_, s_ + 365 * 86400.0) for s_ in roll2]; y = np.array([v[0] for v in Y]); dd = np.array([v[1] for v in Y])
    cut = np.mean([v[4] / max(v[6], 1) for v in Y]) * 100; skip = np.mean([v[5] / max(v[6], 1) for v in Y]) * 100; wst = np.median([v[7] for v in Y]) * 100
    l = f(ts(2025, 10), ts(2026, 10)); l26 = f(ts(2026, 1), ts(2026, 10))
    print(f"{nm:34s} 10% ${np.percentile(y, 10):>6,.0f} медиана ${np.median(y):>7,.0f} 90% ${np.percentile(y, 90):>7,.0f} просадка {np.median(dd)*100:.0f}% | 12 мес ${l[0]:>7,.0f} | 2026 ${l26[0]:>7,.0f} | урезано {cut:.0f}% пропущено {skip:.0f}% сделок | все стопы разом {wst:.0f}% счёта", flush=True)
st("изолированная, плечо по стопу (сейчас)")
st("изолированная, до 50x по стопу", lcap=50)
for L in (10, 20, 25, 50):
    st(f"кросс, плечо {L}x", levf=L)
print("fin")
