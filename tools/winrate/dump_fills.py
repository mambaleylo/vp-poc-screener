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

m = (MD == 0) & (TE != T0)
np.savez("dlm_fills.npz", te=TE[m].astype(np.int64), side=SD[m], r=R[m], t1=T1[m])
print("saved", int(m.sum()))
