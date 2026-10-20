"""Does the score rank the trades within each chart / side? R by score band (score minus the q97 threshold), fills only."""
import numpy as np
import ema_h as E
d = E.d
idx = E.cand(0.80)
R, K, KD = E.outcomes(idx)
thr = np.array([E.THR[y][0.97] for y in E.YR[idx]])
rel = E.SC[idx] - thr
r = R[idx]
bands = ((-0.3, -0.2), (-0.2, -0.1), (-0.1, 0.0), (0.0, 0.05), (0.05, 0.1), (0.1, 0.2), (0.2, 9))
for nm, m in (("4ч", d.tf_s.values[idx] == "4h"), ("день", d.tf_s.values[idx] == "1d"), ("неделя+месяц", np.isin(d.tf_s.values[idx], ("1w", "1M"))),
              ("лонг", d.side.values[idx] > 0), ("шорт", d.side.values[idx] < 0)):
    print(f"{nm:14s} " + " | ".join(f"{a:+.2f}..{b:+.2f}: {np.nanmean(r[m & (rel >= a) & (rel < b)]):+.2f} ({(m & (rel >= a) & (rel < b)).sum()})" for a, b in bands), flush=True)
