"""the yearly walk-forward models of a family (refit as in its wf script, the 127's train coins) applied unchanged to the
extra coins' events; per year WR / R on the extra coins vs the 127's check coins; scores saved"""
import sys; AV = list(sys.argv)
import numpy as np, lightgbm as lgb, warnings; warnings.filterwarnings("ignore")
from s15_wf import load, select, report, fmt
from mk import ts
mod, fam, e = AV[1], AV[2], int(AV[3])
import importlib; E = importlib.import_module(f"{mod}_engine")
D = load(mod, [E.FAMS.index(fam)]); X = load(mod + "x", [E.FAMS.index(fam)])
z = np.load(f"{mod}_sc_{fam}_{e}.npz", allow_pickle=True); SC, THR = z["SC"], z["THR"].item()
T, F, TR = D["t"], D["F"], ~D["chk"]
y = np.clip(D["R"][e], -1.5, 1.5); rng = np.random.default_rng(0)
pr = dict(n_estimators=300, learning_rate=0.05, num_leaves=63, min_child_samples=1000, subsample=0.7, subsample_freq=1, colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
SCX = np.full(len(X["t"]), np.nan)
import os
for Y in ([] if os.path.exists(f"{mod}x_sc_{fam}_{e}.npy") else (2022, 2023, 2024, 2025, 2026)):
    tr = np.flatnonzero(TR & (T < ts(Y) - 3 * 86400))
    if len(tr) < 20000: continue
    if len(tr) > 800000: tr = rng.choice(tr, 800000, replace=False)
    m = lgb.LGBMRegressor(random_state=0, **pr).fit(F[tr], y[tr])
    te = (X["t"] >= ts(Y)) & (X["t"] < ts(Y + 1))
    if te.any(): SCX[te] = m.predict(X["F"][te])
    chk = (T >= ts(Y)) & (T < ts(Y + 1))
    print("year", Y, "same as saved:", float(np.nanmax(np.abs(m.predict(F[chk][:500]) - SC[chk][:500]))), flush=True)
if os.path.exists(f"{mod}x_sc_{fam}_{e}.npy"): SCX = np.load(f"{mod}x_sc_{fam}_{e}.npy")
else: np.save(f"{mod}x_sc_{fam}_{e}.npy", SCX)
OK = np.array([X["names"][k] != "USDCUSDT" for k in X["sym"]])
for q in (0.98, 0.99):
    print(f"{mod} {fam} E{e} q{q}  127-пров: {fmt(report(D, e, select(D, e, SC, THR, q, 12, D['chk'])))}\n{'':24s}  новые 83: {fmt(report(X, e, select(X, e, SCX, THR, q, 12, OK)))}", flush=True)
