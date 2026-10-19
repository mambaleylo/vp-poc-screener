import sys, numpy as np
ARGS = sys.argv[1:]
import pr_hyp as P
q = ARGS[0]
base = P.IDX[P.SC >= (P.T99 if q == "99" else P.T95)]
F, SD = P.F, P.SD
flt = (SD * F["b_r24"] > -4) & (SD * F["b_r1"] > -1)
target = 0.45 if q == "99" else 0.50
grid = [0.01, 0.015, 0.02, 0.025, 0.03, 0.035, 0.04, 0.045, 0.05, 0.055, 0.06, 0.07, 0.08, 0.10, 0.12] if q == "99" else [0.0025, 0.005, 0.0075, 0.01, 0.0125, 0.015, 0.02, 0.03]
print(f"== q {q} (как в боте сейчас: оба фильтра BTC + стоп по закрытию): по графикам")
for nm, m in (("1ч + 4ч (сейчас)", flt), ("только 1ч", flt & (P.TF == 1)), ("только 4ч", flt & (P.TF == 4))):
    tr = P.replay(base[m[base]]); r = P.R[tr]; k = P.KIND[tr]
    run = w = 0
    for j in tr[np.argsort(P.END[tr], kind="stable")]: run = run + 1 if P.KIND[j] in (0, 1) else 0; w = max(w, run)
    yrs = " ".join(f"{r[(P.T[tr] >= P.ts(y)) & (P.T[tr] < P.ts(y + 1))].mean():+.2f}" for y in (2023, 2024, 2025, 2026))
    bs = P.boots(tr, 400); best = None
    for f in grid:
        rr = [P.port(tr, f, b) for b in bs]; ds = np.array([a[1] for a in rr]); xs = np.array([a[0] for a in rr])
        if np.quantile(ds, .9) <= target: best = (f, np.median(xs), np.median(ds), np.quantile(ds, .9))
        else: break
    print(f"{nm:18s} {len(tr):5d} сд. ср.R {r.mean():+.3f} WR {np.mean(r > 0)*100:.0f}% стопов {np.mean(np.isin(k, (0, 1)))*100:.0f}% серия {w:2d} | {yrs} | "
          + (f"риск {best[0]*100:.1f}%: x{best[1]:.1f}, просадка {best[2]*100:.0f}% / {best[3]*100:.0f}%" if best else "—"), flush=True)
