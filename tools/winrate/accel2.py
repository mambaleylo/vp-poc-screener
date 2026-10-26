import numpy as np
exec(open("accel.py").read().split("starts = [")[0])
for m in range(4):
    k = md == m
    print(NM[m], "стоп % медиана", round(np.median(st_[k]) * 100, 2), "авар.стоп % медиана", round(np.median(sth[k]) * 100, 2), "WR", round(np.mean(r_[k] > 0) * 100), "ср.R", round(r_[k].mean(), 2))
for L in (20, 50, 75):
    liq = 1 / L - 0.005
    print(f"x{L}: ликвидация через {liq*100:.1f}% — у {np.mean(st_ > liq)*100:.0f}% сделок обычный стоп дальше ликвидации")
