"""P/R's retrain schedule with its real rules (prv_lab.py's harness: the 1h band events, the bot's own trade as the label, a
model per side, the threshold = q0.99 of the model's scores over the last 12 months of its window, one trade a coin & side, at
most 20 a side, the BTC filter 4% / 1%): Q24 = the last 24 months every quarter (the bot now) vs M24 = the last 24 months
every month (roll_mod.py's best for P/R) vs M0 / Q0 = all history -> trades by year; the lists -> <LABSTORE>/wf/prv_roll_<VAR>.json
usage: prv_roll.py VAR"""
import sys; AV = list(sys.argv)
import os, json, time, numpy as np, lightgbm as lgb
import prv_lab as PL
VAR = AV[1]; STEP = 3 if VAR.startswith("Q") else 1; W = int(VAR[1:]) if VAR[1:] != "0" else 0
z = np.load(f"{PL.ST}/wf/prv_lab_ev.npz"); X, T, SY, LAB, BAR = z["X"], z["T"], z["SY"], z["LAB"], z["BAR"]
SD = X[:, 1].astype(int); lab = LAB[:, 0]; t0 = time.time()
SC = np.full(len(T), np.nan); THR = np.full(len(T), np.inf)
P = []; y, m = 2023, 1
while (y, m) < (2026, 10):
    a0 = PL.ts(y, m); k = m - 1 + STEP; y2, m2 = y + k // 12, k % 12 + 1; P.append((a0, PL.ts(y2, m2) if (y2, m2) <= (2026, 10) else PL.ts(2026, 10))); y, m = y2, m2
for a0, a1 in P:
    tr = (T < a0 - 10 * 86400) & ((T >= a0 - W * 30.4 * 86400 - 10 * 86400) if W else True)
    ref = (T >= a0 - 365 * 86400) & (T < a0 - 10 * 86400); te = (T >= a0) & (T < a1)
    for s in (1, -1):
        ok = tr & (SD == s) & np.isfinite(lab)
        md = lgb.LGBMRegressor(random_state=1, **PL.P).fit(X[ok], np.clip(lab[ok], -1.5, 2.0))
        w = (SD == s) & (ref | te); sc = np.full(len(T), np.nan); sc[w] = md.predict(X[w])
        SC[te & (SD == s)] = sc[te & (SD == s)]; THR[te & (SD == s)] = float(np.nanquantile(sc[ref & (SD == s)], 0.99))
    print(f"{VAR} {np.datetime64(a0, 's')} готов ({time.time() - t0:.0f}s)", flush=True)
b24, b1 = X[:, PL.IB24], X[:, PL.IB1]; okb = ~((SD * b24 <= -4.0) | (SD * b1 <= -1.0))
sel = np.flatnonzero(np.isfinite(SC) & (SC >= THR) & okb)
out = PL.replay(sel, T, SY, SD, LAB[:, 0], BAR[:, 0])
WK = {2023: 52, 2024: 52, 2025: 52, 2026: 39}
yr = lambda t: int(1970 + (t / 86400 + 0.5) / 365.2425)
cells = []
for Y in WK:
    r = [x for t, x in out if yr(t) == Y]; cells.append(f"{Y}: {np.mean(r):+.2f}R {len(r) / WK[Y]:.1f}/нед" if r else f"{Y}: —")
allr = np.array([x for _, x in out]); c = np.cumsum(allr); dd = float(np.max(np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c]))
print(f"ИТОГ P/R {VAR}: {len(allr)} сделок, {allr.mean():+.3f}R, Σ{allr.sum():+.0f}R, просадка {dd:.0f}R | " + " | ".join(cells), flush=True)
json.dump([[int(t), float(x)] for t, x in out], open(f"{PL.ST}/wf/prv_roll_{VAR}.json", "w"))
print("prv roll done", VAR, flush=True)
