"""1h only + both BTC filters: the exits with the stop by close — the take, the soft stop and the hard stop distance.
R per each variant's hard stop (the sizing risk), so the equal-drawdown growth compares them fairly."""
import sys, numpy as np
ARGS = sys.argv[1:]
import pr_hyp as P
import prv_wf as W
q = ARGS[0]
base = P.IDX[(P.SC >= (P.T99 if q == "99" else P.T95))]
base = base[P.TF[base] == 1]
m = (P.SD * P.F["b_r24"] > -4) & (P.SD * P.F["b_r1"] > -1)
cand = base[m[base]]
target = 0.45 if q == "99" else 0.50
grid = ([0.01, 0.015, 0.02, 0.025, 0.03, 0.035, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.12, 0.14, 0.16] if q == "99"
        else [0.0025, 0.005, 0.0075, 0.01, 0.0125, 0.015, 0.02, 0.025, 0.03])
V = [("сейчас: стоп 3 закр. / авар. 6 / тейк 4.5", "prv_lab_cs"), ("тейк 3 ATR", "cs_3_6_3"), ("тейк 3.75 ATR", "cs_3_6_375"),
     ("тейк 6 ATR", "cs_3_6_6"), ("без тейка (48 свечей)", "cs_3_6_x"), ("стоп 2 закр.", "cs_2_6_45"), ("стоп 4 закр.", "cs_4_6_45"),
     ("аварийный 4.5", "cs_3_45_45"), ("аварийный 8", "cs_3_8_45")]
print(f"== q {q}, 1ч, оба фильтра BTC: вариант выхода | сделок, ср.R, WR, минусов подряд | годы | риск и рост при просадке 1 из 10 = {target:.0%}")
for nm, fn in V:
    z = np.load(f"{W.D}/{fn}.npz")
    r = z["cs"].astype(float); P.R = np.where(np.abs(r) > 20, np.nan, r); P.KIND = z["kind"]; P.END = P.T + (z["k"].astype(int) + 1) * P.TF * 3600
    tr = P.replay(cand); rr_ = P.R[tr]; run = w = 0
    for j in tr[np.argsort(P.END[tr], kind="stable")]: run = run + 1 if P.R[j] < 0 else 0; w = max(w, run)
    yrs = " ".join(f"{rr_[(P.T[tr] >= P.ts(y)) & (P.T[tr] < P.ts(y + 1))].mean():+.2f}" for y in (2023, 2024, 2025, 2026))
    bs = P.boots(tr, 250); best = None
    for f in grid:
        out = [P.port(tr, f, b) for b in bs]; ds = np.array([a[1] for a in out])
        if np.quantile(ds, .9) <= target: best = (f, np.median([a[0] for a in out]), np.median(ds))
        else: break
    print(f"{nm:40s} {len(tr):5d} {rr_.mean():+.3f} {np.mean(rr_ > 0)*100:3.0f}% {w:2d} | {yrs} | " + (f"{best[0]*100:5.2f}%: x{best[1]:8.1f} (обычная {best[2]*100:.0f}%)" if best else "—"), flush=True)
