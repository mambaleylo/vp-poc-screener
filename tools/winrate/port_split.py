"""the open-risk cap split: the other modules (P/R / SMC / EMA) at most HO of the equity, ⚡ at most HD, all <= HMAX (v0.99.718 risks). Was: v0.99.717 regime (cross 10x, the open risk <= 90%): re-check what the margin had decided — 📈 Breakout as a 5th module, the modules' risks, ⚡'s 20 cap. Was: the margin binds (the user: "ты прав про то, что надолго маржу задерживает"): isolated margin with the leverage by the
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
src = src.replace(", HMAX, DCAP):", ", HMAX, DCAP, HO, HD):")
src = src.replace("slot = -1; used = 0.0; ndlm = 0; busy = False; heat = 0.0", "slot = -1; used = 0.0; ndlm = 0; busy = False; heat = 0.0; heat_o = 0.0; heat_d = 0.0")
src = src.replace("                used += po_m[k]; heat += po_h[k]\n", "                used += po_m[k]; heat += po_h[k]\n                if po_d[k] == 0: heat_d += po_h[k]\n                else: heat_o += po_h[k]\n")
src = src.replace("hn = ru * STH[j] / ST[j]; fh = HMAX * eq - heat", "hn = ru * STH[j] / ST[j]; fh = HMAX * eq - heat\n            if MD[j] != 0 and HO > 0: fh = min(fh, HO * eq - heat_o)\n            if MD[j] == 0 and HD > 0: fh = min(fh, HD * eq - heat_d)")
assert "heat_o += po_h[k]" in src and "HO * eq - heat_o" in src
assert "ndlm >= DCAP" in src
assert "ncut += 1" in src and "nskip += 1" in src and "LEVF > 0" in src and "worst = hl / eq" in src
exec(src)
WB0 = W_abs(-3, 22)
BB2 = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))
RB = []
for t in BB2["rbx"]:
    if t.get("r") is None or not t.get("x") or not t.get("e") or not t.get("sl"): continue
    st_ = max(0.002, abs(t["e"] - t["sl"]) / t["e"]); RB.append((float(t.get("f") or t["t"]), float(t["x"]), float(t["r"]), st_, st_, 1.5, 4, cid(t["s"]), 1.0))
OLD = [tuple(x) + (float(w),) for x, w in zip(np.stack([T0, T1, R, ST, STH, BUF, MD, CID], 1), WB0)]
def mk(with_rbx):
    A_ = np.array(sorted(OLD + (RB if with_rbx else [])), float); return A_
ARR = {0: mk(False), 1: mk(True)}
def st(nm, rbx=0, rk=(4.5, 3, 1.5, 1, 0), dcap=20, hmax=0.9, levf=10.0, ho=0.0, hd=0.0):
    A_ = ARR[rbx]; t0, t1, r_, st_, sth, buf, md, ci, wg = A_.T; md = md.astype(np.int64); ci = ci.astype(np.int64)
    use = np.ones(5, np.bool_); rk_ = np.array(rk, float) / 100
    f = lambda a, b: simx(t0, t1, r_, st_, sth, buf, md, ci, use, rk_, int(np.searchsorted(t0, a)), b, 0.05, wg, float(levf), 20.0, float(hmax), float(dcap), float(ho), float(hd))
    Y = [f(s_, s_ + 365 * 86400.0) for s_ in roll2]; y = np.array([v[0] for v in Y]); dd = np.array([v[1] for v in Y])
    l = f(ts(2025, 10), ts(2026, 10)); l26 = f(ts(2026, 1), ts(2026, 10))
    print(f"{nm:40s} 10% ${np.percentile(y, 10):>6,.0f} медиана ${np.median(y):>7,.0f} 90% ${np.percentile(y, 90):>8,.0f} просадка {np.median(dd)*100:.0f}% | 12 мес ${l[0]:>8,.0f} | 2026 ${l26[0]:>7,.0f}", flush=True)
st("v0.99.718 (общий потолок 90%)")
for ho in (0.3, 0.4, 0.5, 0.6):
    st(f"P/R+SMC+EMA <= {ho:.0%}", ho=ho)
for hd in (0.6, 0.7, 0.8):
    st(f"⚡ <= {hd:.0%}", hd=hd)
for hm, ho in ((1.0, 0.4), (1.0, 0.5), (1.1, 0.5)):
    st(f"всего <= {hm:.0%}, P/R+SMC+EMA <= {ho:.0%}", hmax=hm, ho=ho)
print("fin")
