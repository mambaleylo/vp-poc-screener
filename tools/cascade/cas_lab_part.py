"""the label of the deployed rule (a third at +0.7R, the stop to the entry, take 2.5R, 48 h) for every cascade event"""
import numpy as np
from cas_h import T, SY, SD, bars
from cas_part import sim
lab = np.full(len(T), np.nan, np.float32)
order = np.argsort(SY, kind="stable")
cur = None
for j in order:
    sy = int(SY[j])
    if sy != cur:
        O, H, L, C, TOP, BOT, atr, tm = bars(sy); pos = {int(t): i for i, t in enumerate(tm)}; cur = sy
    i = pos.get(int(T[j]))
    if i is None or i + 50 >= len(C) or atr[i] != atr[i]: continue
    r = sim(O, H, L, C, i, int(SD[j]), float(atr[i]), 2.5, 48, 0.7, 0.33)[0]
    lab[j] = r
np.save("cas_lab_part.npy", lab)
print("labels", np.sum(~np.isnan(lab)), "mean", np.nanmean(lab), "win%", np.nanmean(lab > 0))
