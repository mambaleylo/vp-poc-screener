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
DL = float(os.environ.get("HDELAY", "0"))   # the hedge's entry: the touch hour's start + DL hours (1 = after the touch hour closed)
print("T0 on an hour boundary:", float(np.mean(T0[MD == 0] % 3600 == 0)), "· T1 on an hour:", float(np.mean(T1[MD == 0] % 3600 == 0)), "· T1 - T0 h median", float(np.median((T1 - T0)[MD == 0]) / 3600), flush=True)
# v2: the fill's own 15m bar (the alt's 15m candles: the first in the touch hour reaching the fill price), the hedge at that
# bar's close (BTC's 15m close) + DL hours
import os as _os
FILL = {}
for p in PC: FILL[(int(p[0]), cid(p[5]["sym"]))] = (float(p[5]["fill"]), int(p[5]["s"]), p[5]["sym"])
M15 = {}
def m15(sym):
    if sym not in M15:
        f = f"data/15m/{sym}.csv"
        if not _os.path.exists(f): M15[sym] = None
        else:
            a = np.loadtxt(f, delimiter=",", ndmin=2); M15[sym] = (a[:, 0].astype(np.int64), a[:, 2], a[:, 3], a[:, 4])
    return M15[sym]
b15 = m15("BTCUSDT")
def btc15(t):   # BTC's close of the 15m bar ending at t (t on a 15m boundary)
    i = int(np.searchsorted(b15[0], t - 900)); return b15[3][i] if i < len(b15[0]) and b15[0][i] == t - 900 else bpx(t)
nf = 0; TE = T0.copy()
for i in range(len(T0)):
    if MD[i] != 0: continue
    v = FILL.get((int(T0[i]), int(CID[i])))
    if not v: continue
    fp, s_, sym = v; d = m15(sym)
    if d is None: continue
    T_, H_, L_, C_ = d; j0 = int(np.searchsorted(T_, T0[i])); te = None
    for j in range(j0, min(j0 + 4, len(T_))):
        if (L_[j] <= fp * (1 + 1e-9)) if s_ > 0 else (H_[j] >= fp * (1 - 1e-9)):
            te = int(T_[j]) + 900; break
    if te: TE[i] = te; nf += 1
print("the fill's 15m bar found for", nf, "of", int((MD == 0).sum()), "⚡ trades", flush=True)
BR = np.array([bpx(T1[i]) / (btc15(int(TE[i] + DL * 3600)) if MD[i] == 0 and TE[i] != T0[i] else bpx(min(T0[i] + DL * 3600 + 3600, T1[i]))) - 1 if SD[i] != 0 else 0.0 for i in range(len(T0))])
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

YR = T0.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970
m0 = (MD == 0) & (SD != 0)
print(f"DELAY {DL}h: ⚡ R {R0[m0].mean():+.3f} · BTC in R {HB[m0].mean():+.3f} · corr {np.corrcoef(R0[m0], HB[m0])[0, 1]:+.2f} · by year " +
      " ".join(f"{Y}:{HB[m0 & (YR == Y)].mean():+.3f}" for Y in range(2022, 2027)), flush=True)
for nm, hd in (("без хеджа", 0), ("хедж 0.15", 0.15), ("хедж 0.25", 0.25), ("хедж 0.5", 0.5)):
    sth(f"[вход: закрытие 15м исполнения +{DL:g}ч] {nm}", hd, 0)
print("fin")
