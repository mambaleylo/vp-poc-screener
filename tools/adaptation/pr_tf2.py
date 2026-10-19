import numpy as np
import pr_hyp as P
import prv_wf as W
old = W.lab_of(1.5, 3.0)
F, SD = P.F, P.SD
flt = (SD * F["b_r24"] > -4) & (SD * F["b_r1"] > -1)
# where in the score ranking the 4h events stand: R of the 4h / 1h events by score band (all test events, filters on)
sel = P.IDX; sc = P.SC; thr = P.T99
rel = sc - thr
for tf in (1, 4):
    m = (P.TF[sel] == tf) & flt[sel] & ~np.isnan(P.R[sel])
    print(f"\n{tf}ч: средний R (новый выход) / R по старому правилу 1.5 ATR / 3R — по полосам оценки (оценка минус порог 1%)")
    for lo, hi in ((-0.3, -0.2), (-0.2, -0.1), (-0.1, 0.0), (0.0, 0.1), (0.1, 0.3), (0.3, 9)):
        mm = m & (rel >= lo) & (rel < hi)
        j = sel[mm]
        if len(j): print(f"   {lo:+.1f}..{hi:+.1f}: {len(j):6d} событий, новый {np.nanmean(P.R[j]):+.3f}, старый {np.nanmean(old[j]):+.3f}")
tr = P.replay(P.IDX[(P.SC >= P.T99)][flt[P.IDX[(P.SC >= P.T99)]]])
j4 = tr[P.TF[tr] == 4]
print(f"\nсделки 4ч бота ({len(j4)}): новый выход {P.R[j4].mean():+.3f}, старое правило 1.5/3R {np.nanmean(old[j4]):+.3f}")
