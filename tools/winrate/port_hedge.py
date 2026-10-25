"""WRONG — LOOKAHEAD (see port_hedge3.py / port_hedge4.py): the hedge entered at the touch HOUR's open, before the fill; BTC's
fall inside that hour (the same dump that filled the ⚡ limit) counted as the hedge's gain. Honest (the hedge at the fill's
15m close): the median $17 743 -> $11 922 at 0.15 — rejected."""
"""(from port_side) the bundle's one-side cap over ALL four modules (the new coins showed: the money is lost on the days every alt falls
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

# the BTC hedge: a ⚡ / EMA trade opens with an opposite BTC position of h x its notional, closed with it (taker in + out,
# 0.05% each); the R of the trade + the hedge's in its R; the hedge's margin at 20x added to the trade's
a_ = np.loadtxt("data/1h/BTCUSDT.csv", delimiter=",", ndmin=2); BT = a_[:, 0].astype(np.int64); BO = a_[:, 1]; BC = a_[:, 4]
def bpx(t):
    i = int(np.searchsorted(BT, t, side="right")) - 1
    return BO[i] if BT[i] == int(t) // 3600 * 3600 else BC[i]
BR = np.array([bpx(T1[i]) / bpx(T0[i]) - 1 if SD[i] != 0 else 0.0 for i in range(len(T0))])
HB = SD * BR / ST   # the BTC move in the trade's R, signed by the trade's side
R0 = R.copy()
src2 = open("port_expect2.py").read(); src2 = "@njit\ndef simp" + src2.split("@njit\ndef simp")[1].split("\nroll2")[0]
src2 = src2.replace("def simp(T0, T1, R, ST, STH, BUF, MD, CID, use, risk, i0, tend, minn, WGT):", "def simh(T0, T1, R, ST, STH, BUF, MD, CID, use, risk, i0, tend, minn, WGT, MX):")
src2 = src2.replace("m = ru / ST[j] / lev;", "m = ru / ST[j] / lev * MX[j];")
assert "MX[j]" in src2
exec(src2)
def sth(nm, hd, he, fee=0.001, use=(1, 1, 1, 1), rk=(4, 2, 1.5, 1)):
    global R
    h = np.where(MD == 0, hd, np.where(MD == 3, he, 0.0)) * (SD != 0)
    R = R0 - h * HB - h * fee / ST
    lev = np.minimum(20.0, np.floor(1.0 / (BUF * STH + 0.0105)))
    MX = 1.0 + h * np.maximum(lev, 1.0) / 20.0
    use = np.array(use, np.bool_); rk = np.array(rk, float) / 100; WG = W_abs(-3, 22)
    f = lambda a, b: simh(T0, T1, R, ST, STH, BUF, MD, CID, use, rk, int(np.searchsorted(T0, a)), b, 0.05, WG, MX)
    Y = [f(s_, s_ + 365 * 86400.0) for s_ in roll2]; y = np.array([v[0] for v in Y]); dd = np.array([v[1] for v in Y])
    l = f(ts(2025, 10), ts(2026, 10)); l26 = f(ts(2026, 1), ts(2026, 10))
    print(f"{nm:44s} 10% ${np.percentile(y, 10):>6,.0f} медиана ${np.median(y):>7,.0f} 90% ${np.percentile(y, 90):>7,.0f} просадка {np.median(dd)*100:.0f}% (90%: {np.percentile(dd, 90)*100:.0f}%) | 12 мес ${l[0]:>7,.0f} | 2026 ${l26[0]:>7,.0f}", flush=True)
    R = R0.copy()
print("⚡ R", R0[MD == 0].mean().round(3), "BTC in R", HB[MD == 0].mean().round(3), "| EMA", R0[MD == 3].mean().round(3), HB[MD == 3].mean().round(3), flush=True)
sth("без хеджа", 0, 0)
for hd in (0.25, 0.5, 0.75, 1.0):
    sth(f"хедж ⚡ {hd}", hd, 0)
sth("хедж ⚡ 0.5 + EMA 0.5", 0.5, 0.5)
sth("хедж ⚡ 1.0 + EMA 1.0", 1.0, 1.0)
sth("хедж ⚡ 0.5, комиссия x2 (проскальзывание)", 0.5, 0, fee=0.002)
for rk in (5, 6):
    sth(f"хедж ⚡ 0.5, ⚡ риск {rk}%", 0.5, 0, rk=(rk, 2, 1.5, 1))
sth("без хеджа, ⚡ риск 3%", 0, 0, rk=(3, 2, 1.5, 1))
print("fin")
