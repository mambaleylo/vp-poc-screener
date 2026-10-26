"""the lifters (Breakout, Cascade, SMC 8h/12h longs) only when the core is idle — causal gates on the day before the
trade: (b) BTC's 30-day realized volatility < its median of the previous 365 days; (d) ⚡'s trades started in the last 30
days < that count's median of the previous 365 days; (r) the core's (⚡ P/R SMC EMA HTF) R closed in the last 30 days
< its median of the previous 365 days; (h) a lifter opens only while the open risk < x of the equity. Friction -0.03R."""
import numpy as np, json, warnings; warnings.filterwarnings("ignore")
exec(open("quiet3.py").read().split("ref, rd, rl = go(")[0])
s9 = s8.replace("def sim8(", "def sim9(").replace(", HMAX, DCAP, TBR):", ", HMAX, DCAP, TBR, LHC):")
s9 = s9.replace("ru = eq * risk[MD[j]] * WGT[j]\n", "ru = eq * risk[MD[j]] * WGT[j]\n        if MD[j] >= 5 and LHC > 0 and heat > LHC * eq: ru = 0.0\n", 1)
assert "LHC * eq" in s9
exec(s9)
# ---- the daily regime series (each day: what was known at its start) ----
D0, D1 = ts(2021, 1) // 86400, ts(2026, 11) // 86400; ND = D1 - D0
bT, bO, bH, bL, bC, bV = LE.load_np("BTCUSDT") if "LE" in dir() else __import__("lv_engine").load_np("BTCUSDT")
dd_ = bT // 86400; dk = np.unique(dd_); dcl = np.array([bC[dd_ == d][-1] for d in dk])
lr = np.r_[np.nan, np.diff(np.log(dcl))]
vol = np.full(ND, np.nan)
for i, d in enumerate(dk):
    if d + 1 - D0 >= ND or i < 30: continue
    if d + 1 - D0 >= 0: vol[d + 1 - D0] = np.nanstd(lr[i - 29:i + 1])       # known at the start of day d+1
vol = np.array([vol[i] if np.isfinite(vol[i]) else (vol[i - 1] if i else np.nan) for i in range(ND)])
for i in range(1, ND):
    if not np.isfinite(vol[i]): vol[i] = vol[i - 1]
t0b, t1b, rb, mdb = B[:, 0], B[:, 1], B[:, 2], B[:, 6].astype(int)
cnt = np.zeros(ND); rr = np.zeros(ND)
s0 = (t0b // 86400 - D0).astype(int); e0 = (t1b // 86400 - D0).astype(int)
ok = (s0 >= 0) & (s0 < ND) & (mdb == 0); np.add.at(cnt, s0[ok], 1)
RKc = np.array([4.5, 3, 2.5, 2, 2.0])
ok = (e0 >= 0) & (e0 < ND); np.add.at(rr, e0[ok], (rb * RKc[mdb])[ok])
def trail(x, w=30):   # the sum over the previous w days (days < today)
    c = np.r_[0, np.cumsum(x)]; i = np.arange(ND); return c[i] - c[np.maximum(i - w, 0)]
cnt30, r30 = trail(cnt), trail(rr)
def below_med(x):   # x[today] < median of x over the previous 365 days
    out = np.zeros(ND, bool)
    for i in range(400, ND): out[i] = x[i] < np.nanmedian(x[i - 365:i])
    return out
GATE = {"b": below_med(vol), "d": below_med(cnt30), "r": below_med(r30)}
for k, g in GATE.items():
    yrs = {Y: round(float(g[(ts(Y) // 86400 - D0):(ts(Y + 1) // 86400 - D0)].mean()), 2) for Y in range(2023, 2027)}
    print(f"ворота {k}: доля дней открыто по годам {yrs}", flush=True)
def gated(parts, gk, wlow=0.0):
    A = [B]
    for p in parts:
        Xp = X[p].copy()
        if gk:
            di = (Xp[:, 0] // 86400 - D0).astype(int).clip(0, ND - 1); Xp[:, 8] = np.where(GATE[gk][di], 1.0, wlow)
        A.append(Xp)
    return np.vstack(A)
def go2(A, rk, lhc=0.0):
    A = A[np.argsort(A[:, 0], kind="stable")]
    t0, t1, r_, st_, sth, buf, md, ci, wg, tbr = A.T; md = md.astype(np.int64); ci = ci.astype(np.int64); r_ = np.where(md != 0, r_ - 0.03, r_)
    use = np.ones(8, np.bool_); rk_ = np.array(rk, float) / 100
    f = lambda a, b: sim9(t0, t1, r_, st_, sth, buf, md, ci, use, rk_, int(np.searchsorted(t0, a)), b, 0.05, wg, 10.0, 20.0, 0.9, 20.0, tbr, lhc)
    Y = [f(s_, s_ + 365 * 86400.0) for s_ in roll2]
    return np.array([v[0] for v in Y]), np.array([v[1] for v in Y]), f(ts(2025, 10), ts(2026, 10))[0]
ref, rd, rl = go2(B, BASE_RK + [0, 0, 0])
def show(nm, A, rk, lhc=0.0):
    y, d, l = go2(A, BASE_RK + rk, lhc); q = y / ref
    print(f"  {nm:40s} 10% ${np.percentile(y, 10):>6,.0f} 25% ${np.percentile(y, 25):>6,.0f} медиана ${np.median(y):>7,.0f} 90% ${np.percentile(y, 90):>8,.0f} | 2023-е мед ${np.median(y[q23]):>6,.0f} | просадка {np.median(d)*100:.0f}% | 12 мес ${l:>8,.0f} | окон лучше {np.mean(q > 1)*100:3.0f}% с дек.24 {np.mean(q[rec] > 1)*100:3.0f}% ×{np.median(q[rec]):.2f} худш ×{q.min():.2f}", flush=True)
print(f"  {'как сейчас':40s} 10% ${np.percentile(ref, 10):>6,.0f} 25% ${np.percentile(ref, 25):>6,.0f} медиана ${np.median(ref):>7,.0f} 90% ${np.percentile(ref, 90):>8,.0f} | 2023-е мед ${np.median(ref[q23]):>6,.0f} | просадка {np.median(rd)*100:.0f}% | 12 мес ${rl:>8,.0f}", flush=True)
for nm, parts, rk in (("Пробой 1 + Каскад 1", ["rbx", "cas"], [0, 1, 1]), ("Пробой 1.5 + Каскад 1.5", ["rbx", "cas"], [0, 1.5, 1.5]),
                      ("SMC812L 2 + Пробой 1.5 + Каскад 1", ["smc812L", "rbx", "cas"], [2, 1.5, 1])):
    print("==", nm, flush=True)
    show("всегда", gated(parts, None), rk)
    for gk, gn in (("b", "BTC тихий"), ("d", "⚡ простаивает"), ("r", "связка мало заработала")):
        show(f"только когда {gn}", gated(parts, gk), rk)
        show(f"когда {gn} ×1, иначе ×0.3", gated(parts, gk, 0.3), rk)
    for h in (0.3, 0.5):
        show(f"только пока открытый риск < {int(h*100)}%", gated(parts, None), rk, h)
