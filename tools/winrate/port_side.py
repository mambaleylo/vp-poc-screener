"""the bundle's one-side cap over ALL four modules (the new coins showed: the money is lost on the days every alt falls
together) — at most N positions a side (⚡ + P/R + SMC + EMA), and a lower risk once K are open a side; v0.99.712 rules"""
exec(open("port_w712.py").read().split("U = [1, 1, 1, 1]")[0])
SMCF, EMAF = "smcqx_0.993_3.0_96_1.0_2.0_4.npy", "emaqr_0.96_1.5_4.npy"
rebuild(SMCF, EMAF)
SIDE = {}; BB = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))   # the current lists (B has the v699 ones)
for p in PC: SIDE[(int(p[0]), cid(p[5]["sym"]))] = int(p[5]["s"])
for t in B["prv"]:
    if t.get("r") is not None: SIDE[(int(t.get("f") or t["t"]), cid(t["s"]))] = int(t["d"])
for nm, arr, ti_c, r_c, names in (("smc", np.load(SMCF), 1, 3, lambda x: SMC_NAMES[int(x[6])]), ("emx", np.load(EMAF), 0, 2, None)):
    keys = {}
    for t in BB[nm]:
        for k in ("f", "t"):
            if t.get(k): keys.setdefault((int(t[k]), round(t["r"], 2)), t["d"])
    nmj = json.load(open(EMAF.replace(".npy", ".json"))) if nm == "emx" else None
    for i, x in enumerate(arr):
        s_ = keys.get((int(x[ti_c]), round(float(x[r_c]), 2)))
        if s_ is not None: SIDE[(int(x[ti_c]), cid(names(x) if names else nmj[i]))] = int(s_)
SD = np.array([SIDE.get((int(T0[i]), int(CID[i])), 0) for i in range(len(T0))], np.int64)
print("rows", len(T0), "with a side", int((SD != 0).sum()), {m: int(((SD != 0) & (MD == m)).sum()) for m in range(4)}, {m: int((MD == m).sum()) for m in range(4)}, flush=True)
src = open("port_expect2.py").read(); src = "@njit\ndef simp" + src.split("@njit\ndef simp")[1].split("\nroll2")[0]
src = src.replace("def simp(T0, T1, R, ST, STH, BUF, MD, CID, use, risk, i0, tend, minn, WGT):", "def simq(T0, T1, R, ST, STH, BUF, MD, CID, use, risk, i0, tend, minn, WGT, SD, cap, kside, kmul):")
src = src.replace("po_d = np.zeros(N, np.int64)", "po_d = np.zeros(N, np.int64); po_s = np.zeros(N, np.int64)")
src = src.replace("slot = -1; used = 0.0; ndlm = 0; busy = False", "slot = -1; used = 0.0; ndlm = 0; busy = False; nside = 0")
src = src.replace("                if po_c[k] == CID[j]: busy = True", "                if po_c[k] == CID[j]: busy = True\n                if SD[j] != 0 and po_s[k] == SD[j]: nside += 1")
src = src.replace("if slot < 0 or busy or (MD[j] == 0 and ndlm >= 20):", "if slot < 0 or busy or (MD[j] == 0 and ndlm >= 20) or nside >= cap:")
src = src.replace("ru = eq * risk[MD[j]] * WGT[j];", "ru = eq * risk[MD[j]] * WGT[j] * (kmul if nside >= kside else 1.0);")
src = src.replace("po_d[slot] = MD[j];", "po_d[slot] = MD[j]; po_s[slot] = SD[j];")
assert src.count("nside") >= 4 and "po_s[slot]" in src
exec(src)
def st3(nm, cap=999, kside=999, kmul=1.0, use=(1, 1, 1, 1), rk=(4, 2, 1.5, 1)):
    use = np.array(use, np.bool_); rk = np.array(rk, float) / 100; WG = W_abs(-3, 22)
    f = lambda a, b: simq(T0, T1, R, ST, STH, BUF, MD, CID, use, rk, int(np.searchsorted(T0, a)), b, 0.05, WG, SD, cap, kside, kmul)
    Y = [f(s_, s_ + 365 * 86400.0) for s_ in roll2]; y = np.array([v[0] for v in Y]); dd = np.array([v[1] for v in Y])
    l = f(ts(2025, 10), ts(2026, 10)); l26 = f(ts(2026, 1), ts(2026, 10))
    print(f"{nm:42s} 10% ${np.percentile(y, 10):>6,.0f} медиана ${np.median(y):>7,.0f} 90% ${np.percentile(y, 90):>7,.0f} просадка {np.median(dd)*100:.0f}% (90%: {np.percentile(dd, 90)*100:.0f}%) | 12 мес ${l[0]:>7,.0f} | 2026 ${l26[0]:>7,.0f}", flush=True)
st3("сейчас (без общего лимита)")
for cap in (20, 16, 14, 12, 10, 8):
    st3(f"не больше {cap} позиций в одну сторону", cap=cap)
for ks, km in ((8, 0.75), (8, 0.5), (12, 0.75), (12, 0.5), (16, 0.5)):
    st3(f"от {ks} в одну сторону риск x{km}", kside=ks, kmul=km)
print("fin")
