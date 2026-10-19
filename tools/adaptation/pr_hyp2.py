"""Equal-pain comparison: for each variant the risk at which the 1-in-10 drawdown reaches the target, and the growth there."""
import sys, numpy as np
ARGS = sys.argv[1:]
import pr_hyp as P
q = ARGS[0]
base = P.IDX[P.SC >= (P.T99 if q == "99" else P.T95)]
F, SD = P.F, P.SD
btc = SD * F["b_r24"] > -4
b1 = SD * F["b_r1"]
target = 0.45 if q == "99" else 0.50
grid = [0.01, 0.015, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.10, 0.12, 0.15] if q == "99" else [0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.03]
V = [("BTC 24ч 4% (в боте)", base[btc[base]], {})]
for lim in (0.5, 1.0, 1.5, 2.0):
    V.append((f"+ BTC 1ч против > {lim}%", base[(btc & (b1 > -lim))[base]], {}))
V += [("+ не больше 1 входа в сторону за час", base[btc[base]], {"per_hour": 1}),
      ("+ не больше 2 входов в сторону за час", base[btc[base]], {"per_hour": 2}),
      ("+ BTC 1ч 1% + 1 вход за час", base[(btc & (b1 > -1))[base]], {"per_hour": 1}),
      ("+ по тренду дня (EMA200)", base[(btc & (SD * F["dd_e200"] > 0))[base]], {}),
      ("+ ADX < 30", base[(btc & (F["adx"] < 30))[base]], {})]
print(f"== q {q}: риск, при котором просадка 1 из 10 = {target:.0%}, и рост за 2023–26 при нём")
for nm, cand, kw in V:
    tr = P.replay(cand, **kw); bs = P.boots(tr, 300)
    best = None
    for f in grid:
        rr = [P.port(tr, f, b) for b in bs]; ds = np.array([a[1] for a in rr]); xs = np.array([a[0] for a in rr])
        d90 = np.quantile(ds, .9)
        if d90 <= target: best = (f, np.median(xs), np.median(ds), d90, ds.max())
        else: break
    r = P.R[tr]
    print(f"{nm:40s} {len(tr):5d} сд. ср.R {r.mean():+.3f} WR {np.mean(r > 0) * 100:.0f}% | " + (f"риск {best[0]*100:.2f}%: x{best[1]:.1f}, просадка {best[2]*100:.0f}% / {best[3]*100:.0f}% / худшая {best[4]*100:.0f}%" if best else "—"), flush=True)
