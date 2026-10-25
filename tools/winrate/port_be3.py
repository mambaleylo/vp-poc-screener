"""break-even for P/R / SMC to free the open-risk room (be_heat.json): after +X R the stop at the entry -> its open risk 0 from then, its R / exit as walked; the v0.99.718 regime. Was: v0.99.717 regime (cross 10x, the open risk <= 90%): re-check what the margin had decided — 📈 Breakout as a 5th module, the modules' risks, ⚡'s 20 cap. Was: the margin binds (the user: "ты прав про то, что надолго маржу задерживает"): isolated margin with the leverage by the
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
src = src.replace("po_d[slot] = MD[j]; nmod[MD[j]] += 1", "po_d[slot] = MD[j]; nmod[MD[j]] += 1\n        hl = 0.0\n        for k in range(N):\n            if on[k]: hl += po_u[k] * STH[j] / ST[j] if k == slot else po_u[k] * 1.5\n        if eq > 1e-9 and hl / eq > worst: worst = hl / eq")
src = src.replace("return (eq - deps) * 100 + 100, mdd, nmod, rmod * 100", "return (eq - deps) * 100 + 100, mdd, nmod, rmod * 100, ncut, nskip, ntot, worst")
src = src.replace(", LEVF, LCAP):", ", LEVF, LCAP, HMAX):")
src = src.replace("po_d = np.zeros(N, np.int64)", "po_d = np.zeros(N, np.int64); po_h = np.zeros(N)")
src = src.replace("slot = -1; used = 0.0; ndlm = 0; busy = False", "slot = -1; used = 0.0; ndlm = 0; busy = False; heat = 0.0")
src = src.replace("                used += po_m[k]\n", "                used += po_m[k]; heat += po_h[k]\n")
src = src.replace("ru = eq * risk[MD[j]] * WGT[j]; m = ru / ST[j] / lev;", "ru = eq * risk[MD[j]] * WGT[j]\n        if HMAX > 0:\n            hn = ru * STH[j] / ST[j]; fh = HMAX * eq - heat\n            if hn > fh and hn > 0: ru = ru * max(fh, 0.0) / hn\n        m = ru / ST[j] / lev;")
src = src.replace("po_d[slot] = MD[j];", "po_d[slot] = MD[j]; po_h[slot] = ru * STH[j] / ST[j];")
assert "heat += po_h[k]" in src and "po_h[slot]" in src and "HMAX > 0" in src, [x in src for x in ("heat += po_h[k]", "po_h[slot]", "HMAX > 0")]
src = src.replace("        if m > free:", "        if m > free and m > 0:")
src = src.replace("nmod = np.zeros(4); rmod = np.zeros(4)", "nmod = np.zeros(5); rmod = np.zeros(5)").replace(", LEVF, LCAP, HMAX):", ", LEVF, LCAP, HMAX, DCAP):").replace("(MD[j] == 0 and ndlm >= 20)", "(MD[j] == 0 and ndlm >= DCAP)")
src = src.replace(", HMAX, DCAP):", ", HMAX, DCAP, TBR):")
src = src.replace("po_d = np.zeros(N, np.int64); po_h = np.zeros(N)", "po_d = np.zeros(N, np.int64); po_h = np.zeros(N); po_tb = np.zeros(N)")
src = src.replace("                used += po_m[k]; heat += po_h[k]\n", "                used += po_m[k]\n                if T0[j] < po_tb[k]: heat += po_h[k]\n")
src = src.replace("po_h[slot] = ru * STH[j] / ST[j];", "po_h[slot] = ru * STH[j] / ST[j]; po_tb[slot] = TBR[j];")
assert "po_tb[slot] = TBR[j]" in src and "if T0[j] < po_tb[k]" in src
assert "ndlm >= DCAP" in src
assert "ncut += 1" in src and "nskip += 1" in src and "LEVF > 0" in src and "worst = hl / eq" in src
exec(src)
WB0 = W_abs(-3, 22)
BE = json.load(open("be_heat2.json"))
BB2 = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))
CNAME = {v: k for k, v in coins.items()}
def build(cfg):   # cfg: {MD: X} -> rows with the break-even applied
    rows = []
    for i in range(len(T0)):
        t0, t1, r, md = float(T0[i]), float(T1[i]), float(R[i]), int(MD[i]); tb = 1e18
        name = {1: "prv", 2: "smc", 3: "emx"}.get(md)
        if name and md in cfg:
            v = BE[str(cfg[md])][name].get(f"{CNAME[int(CID[i])]}_{int(t0)}_{round(r, 2)}")
            if v: tb, r, t1 = float(v[0]), float(v[1]), float(v[2])
        rows.append((t0, t1, r, float(ST[i]), float(STH[i]), float(BUF[i]), md, int(CID[i]), float(WB0[i]), tb))
    return np.array(sorted(rows), float)
def st(nm, cfg, rk=(4.5, 3, 1.5, 1)):
    A_ = build(cfg); t0, t1, r_, st_, sth, buf, md, ci, wg, tbr = A_.T; md = md.astype(np.int64); ci = ci.astype(np.int64)
    use = np.ones(4, np.bool_); rk_ = np.array(rk, float) / 100
    f = lambda a, b: simx(t0, t1, r_, st_, sth, buf, md, ci, use, rk_, int(np.searchsorted(t0, a)), b, 0.05, wg, 10.0, 20.0, 0.9, 20.0, tbr)
    Y = [f(s_, s_ + 365 * 86400.0) for s_ in roll2]; y = np.array([v[0] for v in Y]); dd = np.array([v[1] for v in Y])
    l = f(ts(2025, 10), ts(2026, 10)); l26 = f(ts(2026, 1), ts(2026, 10))
    nmatch = int(np.sum(tbr < 1e17))
    print(f"{nm:30s} 10% ${np.percentile(y, 10):>6,.0f} медиана ${np.median(y):>7,.0f} 90% ${np.percentile(y, 90):>8,.0f} просадка {np.median(dd)*100:.0f}% | 12 мес ${l[0]:>8,.0f} | 2026 ${l26[0]:>7,.0f} | безубыток у {nmatch} сделок", flush=True)
st("v0.99.718 (без безубытка)", {})
st("SMC +2R (как в боте)", {2: 2.0})
print("fin")
