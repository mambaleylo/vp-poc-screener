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
src = src.replace(", LEVF, LCAP):", ", LEVF, LCAP, HMAX):")
src = src.replace("po_d = np.zeros(N, np.int64)", "po_d = np.zeros(N, np.int64); po_h = np.zeros(N)")
src = src.replace("slot = -1; used = 0.0; ndlm = 0; busy = False", "slot = -1; used = 0.0; ndlm = 0; busy = False; heat = 0.0")
src = src.replace("                used += po_m[k]\n", "                used += po_m[k]; heat += po_h[k]\n")
src = src.replace("ru = eq * risk[MD[j]] * WGT[j]; m = ru / ST[j] / lev;", "ru = eq * risk[MD[j]] * WGT[j]\n        if HMAX > 0:\n            hn = ru * STH[j] / ST[j]; fh = HMAX * eq - heat\n            if hn > fh: ru = ru * max(fh, 0.0) / hn\n        m = ru / ST[j] / lev;")
src = src.replace("po_d[slot] = MD[j];", "po_d[slot] = MD[j]; po_h[slot] = ru * STH[j] / ST[j];")
assert "heat += po_h[k]" in src and "po_h[slot]" in src and "HMAX > 0" in src, [x in src for x in ("heat += po_h[k]", "po_h[slot]", "HMAX > 0")]
assert "ncut += 1" in src and "nskip += 1" in src and "LEVF > 0" in src and "worst = hl / eq" in src
exec(src)
WB = W_abs(-3, 22)
def st(nm, levf=0.0, lcap=20.0, hmax=0.0, use=(1, 1, 1, 1), rk=(4, 2, 1.5, 1)):
    use = np.array(use, np.bool_); rk = np.array(rk, float) / 100
    f = lambda a, b: simx(T0, T1, R, ST, STH, BUF, MD, CID, use, rk, int(np.searchsorted(T0, a)), b, 0.05, WB, float(levf), float(lcap), float(hmax))
    Y = [f(s_, s_ + 365 * 86400.0) for s_ in roll2]; y = np.array([v[0] for v in Y]); dd = np.array([v[1] for v in Y])
    cut = np.mean([v[4] / max(v[6], 1) for v in Y]) * 100; skip = np.mean([v[5] / max(v[6], 1) for v in Y]) * 100; wst = np.median([v[7] for v in Y]) * 100
    l = f(ts(2025, 10), ts(2026, 10)); l26 = f(ts(2026, 1), ts(2026, 10))
    print(f"{nm:34s} 10% ${np.percentile(y, 10):>6,.0f} медиана ${np.median(y):>7,.0f} 90% ${np.percentile(y, 90):>7,.0f} просадка {np.median(dd)*100:.0f}% | 12 мес ${l[0]:>7,.0f} | 2026 ${l26[0]:>7,.0f} | урезано {cut:.0f}% пропущено {skip:.0f}% сделок | все стопы разом {wst:.0f}% счёта", flush=True)
use = np.ones(4, np.bool_); rk = np.array([4, 2, 1.5, 1], float) / 100
def ys(levf, hmax):
    return np.array([simx(T0, T1, R, ST, STH, BUF, MD, CID, use, rk, int(np.searchsorted(T0, s_)), s_ + 365 * 86400.0, 0.05, WB, float(levf), 20.0, float(hmax))[:2] for s_ in roll2])
base = ys(0, 0)
yr0 = (roll2.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970)
for nm, lv, hm in (("кросс 20x, риск <= 70%", 20, 0.7), ("кросс 10x, риск <= 70%", 10, 0.7), ("кросс 15x, риск <= 70%", 15, 0.7), ("кросс 20x, риск <= 85%", 20, 0.85), ("кросс 10x, риск <= 85%", 10, 0.85)):
    v = ys(lv, hm); win = v[:, 0] > base[:, 0]; dd_ = v[:, 1] < base[:, 1]
    print(f"{nm:26s} лучше текущего в {win.mean()*100:.0f}% окон (по году старта: " + " ".join(f"{y}:{win[yr0 == y].mean()*100:.0f}%" for y in sorted(set(yr0))) + f") · просадка меньше в {dd_.mean()*100:.0f}% · медиана отношения x{np.median(v[:, 0] / base[:, 0]):.2f}, худшие 10% отношения x{np.percentile(v[:, 0] / base[:, 0], 10):.2f}", flush=True)
print("fin")
