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

# the BTC cluster trade (module 4): >= K ⚡ long fills within W h (each known at its 15m close) -> BTC long at that close,
# a stop STP below, out after H h; one a day; its own risk
z = np.load("dlm_fills.npz"); TEf, SDf = z["te"], z["side"]
a_ = np.loadtxt("data/15m/BTCUSDT.csv", delimiter=",", ndmin=2); BT = a_[:, 0].astype(np.int64); BH, BL, BC = a_[:, 2], a_[:, 3], a_[:, 4]
pos15 = {int(t): i for i, t in enumerate(BT)}
def cl_rows(K, W, H, STP, side=1):
    ts_ = np.sort(TEf[SDf == side]); out = []; last = -1e18
    for t in ts_:
        if np.sum((ts_ > t - W * 3600) & (ts_ <= t)) >= K and t - last > 86400:
            i = pos15.get(int(t) - 900)
            if i is None or i + H * 4 >= len(BC): continue
            e = BC[i]; sl = e * (1 - side * STP); r = None; te = None
            for j in range(i + 1, i + H * 4 + 1):
                if (BL[j] <= sl) if side > 0 else (BH[j] >= sl):
                    r = -1.0 - 0.0005 / STP; te = BT[j] + 900; break
            if r is None:
                r = side * (BC[i + H * 4] / e - 1) / STP - 0.0009 / STP; te = BT[i + H * 4] + 900
            out.append((float(t), float(te), r, STP, STP, 1.5, 4, cid("BTC_USDT")))
            last = t
    return out
src = open("port_expect2.py").read(); src = "@njit\ndef simp" + src.split("@njit\ndef simp")[1].split("\nroll2")[0]
src = src.replace("if po_c[k] == CID[j]: busy = True", "if po_c[k] == CID[j] and (NOBLK == 0 or (po_d[k] != 4 and MD[j] != 4)): busy = True").replace("def simp(", "def simp5(").replace("nmod = np.zeros(4); rmod = np.zeros(4)", "nmod = np.zeros(5); rmod = np.zeros(5)")
assert "np.zeros(5)" in src
exec(src.replace('def simp5(T0, T1, R, ST, STH, BUF, MD, CID, use, risk, i0, tend, minn, WGT):', 'def simp5(T0, T1, R, ST, STH, BUF, MD, CID, use, risk, i0, tend, minn, WGT, NOBLK):'))
BASE = np.array(np.stack([T0, T1, R, ST, STH, BUF, MD, CID], 1)); WB0 = W_abs(-3, 22)
NB = [0]
def runc(nm, rows_, rk5):
    A_ = np.array(sorted(list(map(tuple, BASE)) + rows_), float)
    t0, t1, r_, st, sth, buf, md, ci = A_.T; md = md.astype(np.int64); ci = ci.astype(np.int64)
    # the weights: the deployed ones for the old rows, 1 for the new
    key = {(float(a), float(b), int(c)): w for a, b, c, w in zip(T0, T1, MD, WB0)}
    wg = np.array([key.get((float(a), float(b), int(c)), 1.0) for a, b, c in zip(t0, t1, md)])
    use = np.array([1, 1, 1, 1, 1], np.bool_); rk = np.array([4, 2, 1.5, 1, rk5], float) / 100
    f = lambda a, b: simp5(t0, t1, r_, st, sth, buf, md, ci, use, rk, int(np.searchsorted(t0, a)), b, 0.05, wg, NB[0])
    Y = [f(s_, s_ + 365 * 86400.0) for s_ in roll2]; y = np.array([v[0] for v in Y]); dd = np.array([v[1] for v in Y])
    l = f(ts(2025, 10), ts(2026, 10)); l26 = f(ts(2026, 1), ts(2026, 10))
    print(f"{nm:40s} 10% ${np.percentile(y, 10):>6,.0f} медиана ${np.median(y):>7,.0f} 90% ${np.percentile(y, 90):>7,.0f} просадка {np.median(dd)*100:.0f}% | 12 мес ${l[0]:>7,.0f} | 2026 ${l26[0]:>7,.0f} | BTC сделок за 12 мес {int(l[2][4])}", flush=True)

BB2 = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))
def mod_rows(k):
    out = []
    for t in BB2[k]:
        if t.get("r") is None or not t.get("x") or not t.get("e") or not t.get("sl"): continue
        ti = float(t.get("f") or t["t"]); st = max(0.002, abs(t["e"] - t["sl"]) / t["e"])
        out.append((ti, float(t["x"]), float(t["r"]), st, st, 1.5, 4, cid(t["s"])))
    return out
RB, CA = mod_rows("rbx"), mod_rows("cas")
print("rbx rows", len(RB), "stop median %.1f%%" % (100 * np.median([x[3] for x in RB])), "| cas rows", len(CA), flush=True)
runc("сейчас", [], 0)
for nb in (0, 1):
    NB[0] = nb
    for rk5 in (0.5, 1, 2):
        runc(f"+ Пробой {rk5}%" + (" (не занимает монеты)" if nb else " (занимает монеты)"), RB, rk5)
# how many ⚡ trades the breakout's open positions block
print("fin")
