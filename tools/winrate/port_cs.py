"""port_cs: the portfolio (⚡ 4, P/R 2, SMC 1, EMA 0.5) with the close-stop variants of SMC / EMA (leverage by the hard stop)"""
"""port699: port697 with the honest EMA / SMC lists (the bot's order of the touches). Was: the user: ⚡ limits + P/R + SMC + EMA together on one account. One account from $100, the cautious -0.025R a trade:
⚡ — the deployed pool (v0.99.695: the chart's close stop, the leverage at the emergency stop with the liquidation 1.25x),
20 positions, 4%; P/R, SMC, EMA — their backtest lists (vp_bt_trades.json; the bot's rules), the leverage by the stop
(P/R: its emergency "hs") with the bot's 1.5x, risk r each; one position a coin over all (Binance one-way); the margin
shared (90% of the free equity; less -> the trade smaller, under $5 at $100 -> not opened). Windows: 12 months from each
week of 2023-01 .. 2025-09, the last 12 months"""
exec(open("closetf7.py").read().split("def money3")[0])
import json
PC = pool(E, mk2(2.0, 3.0, lambda e: e["tfh"]))
norm = lambda s: s.replace("_USDT", "").replace("USDT", "").replace("1000", "")
B = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))
B["emx"] = json.load(open("emx_bt_v699.json")); B["smc"] = json.load(open("smc_bt_v699.json"))   # v0.99.699: the honest lists
MOD = {"dlm": 0, "prv": 1, "smc": 2, "emx": 3}
rows = []   # (t_in, t_out, R, stop frac, hard frac, buf, module, coin id)
coins = {}
cid = lambda s: coins.setdefault(norm(s), len(coins))
for p in PC:
    st = float(p[3]); rows.append((p[0], p[1], p[2], st, st * 1.5, 1.25, 0, cid(p[5]["sym"])))
for m in ("prv", "smc", "emx"):
    for t in B[m]:
        if t.get("r") is None or not t.get("x") or not t.get("e") or not t.get("sl"): continue
        ti = t.get("f") or t["t"]; st = max(0.002, abs(t["e"] - t["sl"]) / t["e"]); hs = abs(t["e"] - t["hs"]) / t["e"] if t.get("hs") else st
        rows.append((ti, t["x"], t["r"], st, hs, 1.5, MOD[m], cid(t["s"])))
A = np.array(sorted(rows), float)
T0, T1, R, ST, STH, BUF, MD, CID = A.T; MD = MD.astype(np.int64); CID = CID.astype(np.int64)
@njit
def simp(T0, T1, R, ST, STH, BUF, MD, CID, use, risk, i0, tend, minn):
    eq = 1.0; peak = 1.0; mdd = 0.0; deps = 1.0; N = 400
    po_t = np.zeros(N); po_r = np.zeros(N); po_m = np.zeros(N); po_u = np.zeros(N); po_c = np.zeros(N, np.int64); po_d = np.zeros(N, np.int64)
    on = np.zeros(N, np.bool_); nmod = np.zeros(4); rmod = np.zeros(4)
    j = i0
    while j < len(T0) and T0[j] < tend:
        if not use[MD[j]]:
            j += 1; continue
        for k in range(N):
            if on[k] and po_t[k] <= T0[j]:
                eq += po_u[k] * (po_r[k] - 0.025); rmod[po_d[k]] += po_u[k] * (po_r[k] - 0.025); on[k] = False
                if eq > peak: peak = eq
                dd = 1 - eq / peak
                if dd > mdd: mdd = dd
        if eq < 0.1:
            eq = 1.0; peak = 1.0; deps += 1.0
            for k in range(N): on[k] = False
        slot = -1; used = 0.0; ndlm = 0; busy = False
        for k in range(N):
            if on[k]:
                used += po_m[k]
                if po_d[k] == 0: ndlm += 1
                if po_c[k] == CID[j]: busy = True
            elif slot < 0: slot = k
        if slot < 0 or busy or (MD[j] == 0 and ndlm >= 20):
            j += 1; continue
        lev = min(20.0, np.floor(1.0 / (BUF[j] * STH[j] + 0.0105)))
        if lev < 1.0:
            j += 1; continue
        ru = eq * risk[MD[j]]; m = ru / ST[j] / lev; free = (eq - used) * 0.9
        if m > free:
            ru = ru * max(free, 0.0) / m; m = max(free, 0.0)
        if ru / ST[j] < minn:
            j += 1; continue
        on[slot] = True; po_t[slot] = T1[j]; po_r[slot] = R[j]; po_m[slot] = m; po_u[slot] = ru; po_c[slot] = CID[j]; po_d[slot] = MD[j]; nmod[MD[j]] += 1
        j += 1
    for k in range(N):
        if on[k]:
            eq += po_u[k] * (po_r[k] - 0.025); rmod[po_d[k]] += po_u[k] * (po_r[k] - 0.025)
    if eq < 0: eq = 0.0
    return (eq - deps) * 100 + 100, mdd, nmod, rmod * 100
roll2 = np.arange(ts(2023, 2), ts(2025, 10) + 1, 7 * 86400.0)
def run(nm, use, rk):
    use = np.array(use, np.bool_); rk = np.array(rk, float) / 100
    Y = [simp(T0, T1, R, ST, STH, BUF, MD, CID, use, rk, int(np.searchsorted(T0, s_)), s_ + 365 * 86400.0, 0.05) for s_ in roll2]
    y = np.array([v[0] for v in Y]); dd = np.array([v[1] for v in Y])
    l = simp(T0, T1, R, ST, STH, BUF, MD, CID, use, rk, int(np.searchsorted(T0, ts(2025, 10))), ts(2026, 10), 0.05)
    by = " ".join(f"{n}:{int(l[2][i])} сд/{l[3][i]:+.0f}$" for i, n in enumerate(("⚡", "P/R", "SMC", "EMA")) if use[i])
    print(f"{nm:36s} медиана ${np.median(y):>7,.0f} 10% ${np.percentile(y, 10):>6,.0f} просадка {np.median(dd)*100:.0f}% | 12 мес ${l[0]:>7,.0f} ({by})", flush=True)
    return y

import glob as _g
SMC_NAMES = [os.path.basename(f)[:-4] for f in sorted(_g.glob("lv2/*.npz")) if len(np.load(f)["t"])]
BASE_ROWS = [r_ for r_ in rows if r_[6] in (0, 1)]   # ⚡ and P/R as before
def build(smc_f, ema_f):
    rr = list(BASE_ROWS)
    a = np.load(smc_f)
    for sel, ti, to, R_, st, sth, sy in a:
        rr.append((ti, to, R_, max(0.002, st), max(0.002, sth), 1.5, 2, cid(SMC_NAMES[int(sy)])))
    b = np.load(ema_f); nm = json.load(open(ema_f.replace(".npy", ".json")))
    for (ti, to, R_, st, sth), s_ in zip(b, nm):
        rr.append((ti, to, R_, max(0.002, st), max(0.002, sth), 1.5, 3, cid(s_)))
    return np.array(sorted(rr), float)
def setrows(Arr):
    global T0, T1, R, ST, STH, BUF, MD, CID
    T0, T1, R, ST, STH, BUF, MD, CID = Arr.T; MD = MD.astype(np.int64); CID = CID.astype(np.int64)

VAR = [("SMC касанием, EMA касанием (сейчас)", "smc_cs_1.0_1.0_0.npy", "ema_cs_0.75_0.npy")]
for kh in (1, 4, 24):
    VAR.append((f"SMC закр.{kh}ч/2, EMA касанием", f"smc_cs_1.0_2.0_{kh}.npy", "ema_cs_0.75_0.npy"))
    VAR.append((f"SMC касанием, EMA закр.{kh}ч/1.5", "smc_cs_1.0_1.0_0.npy", f"ema_cs_1.5_{kh}.npy"))
VAR.append(("SMC закр.4ч/1.5, EMA закр.4ч/1.0", "smc_cs_1.0_1.5_4.npy", "ema_cs_1.0_4.npy"))
VAR.append(("SMC закр.24ч/2, EMA закр.24ч/1.5", "smc_cs_1.0_2.0_24.npy", "ema_cs_1.5_24.npy"))
VAR.append(("SMC закр.4ч/2, EMA закр.4ч/1.5", "smc_cs_1.0_2.0_4.npy", "ema_cs_1.5_4.npy"))
for nm, sf, ef in VAR:
    setrows(build(sf, ef))
    run(nm + " · 4/2/1/0.5", [1, 1, 1, 1], [4, 2, 1, 0.5])
setrows(build("smc_cs_1.0_2.0_4.npy", "ema_cs_1.5_4.npy"))
for rk in ([4, 2, 1.5, 1], [4, 2, 1, 1], [4, 2, 2, 1], [4, 2, 1.5, 0.5]):
    run("SMC закр.4ч/2, EMA закр.4ч/1.5 · " + "/".join(f"{x:g}" for x in rk), [1, 1, 1, 1], rk)
