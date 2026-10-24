"""the bundle with SMC at q 0.99 (deployed) / 0.993 / 0.995 and its risk, the v0.99.704 ⚡ rules"""
exec(open("port_osc3.py").read().split('print("медиана wt')[0])
def rebuild(f, fe="ema_cs_1.5_4.npy"):
    global NO, base, X, xw
    setrows(build(f, fe))
    NO = np.zeros(len(T0), np.int64); dl = np.flatnonzero(MD == 0)
    for k_, i in enumerate(dl):
        prev = dl[:k_]; NO[i] = int(np.sum((T0[prev] <= T0[i]) & (T1[prev] > T0[i])))
    base = W_of(5, 0.625, 1.25); X = {k: col(k) for k in ("wt_1d",)}; xw = X["wt_1d"]

rebuild("smcqr_0.993_1.0_2.0_4.npy", "emaqr_0.96_1.5_4.npy")
Bx = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))
extra = []
for m_, k_ in (("rbx", 4), ("cas", 5)):
    for t in Bx[m_]:
        if t.get("r") is None or not t.get("x"): continue
        ti = float(t.get("f") or t["t"]); st = max(0.002, abs(t["e"] - t["sl"]) / t["e"])
        extra.append((ti, float(t["x"]), float(t["r"]), st, st, 1.5, k_, cid(t["s"])))
base_rows = [tuple(r) for r in np.c_[T0, T1, R, ST, STH, BUF, MD, CID]]
def with_extra(mods):
    rr = base_rows + [e for e in extra if e[6] in mods]
    setrows(np.array(sorted(rr), float))
    global NO, base, X, xw
    NO = np.zeros(len(T0), np.int64); dl = np.flatnonzero(MD == 0)
    for k_, i in enumerate(dl):
        prev = dl[:k_]; NO[i] = int(np.sum((T0[prev] <= T0[i]) & (T1[prev] > T0[i])))
    base = W_of(5, 0.625, 1.25); X = {"wt_1d": col("wt_1d")}; xw = X["wt_1d"]
U6 = [1, 1, 1, 1, 1, 1]
with_extra(()); stats2("сейчас (⚡4 P/R2 SMC1.5 EMA0.5)", U6, [4, 2, 1.5, 0.5, 0, 0], W_abs(-3, 22))
with_extra((4, 5))
for rb, cs in ((0.5, 0), (1, 0), (2, 0), (0, 0.5), (0, 1), (1, 0.5), (2, 1)):
    stats2(f"+ пробой {rb}% + каскад {cs}%", U6, [4, 2, 1.5, 0.5, rb, cs], W_abs(-3, 22))
