"""Strong zones: the deployed scheme's walk-forward scores saved once (all history before each year, yearly, 3 seeds,
label G_0.75_R4.0), for every zone 2022 .. 2026-09, + the q 0.95 (the bot) / q 0.85 (a check set) thresholds -> zm_sel.npz"""
import numpy as np, pandas as pd, lightgbm as lgb
from mk import df, feats, HOLD_S, ts
from common import D
LAB = "G_0.75_R4.0"
d = df([LAB, LAB + "_h"]); F = feats(d)
X = d[F].values.astype(np.float32); T = d.t.values.astype(np.int64)
lab = d[LAB].values.astype(float)
P = dict(n_estimators=500, learning_rate=0.02, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1, colsample_bytree=0.6, reg_lambda=5.0)
sc_all = np.full(len(T), np.nan, np.float32); t95 = np.full(len(T), np.nan, np.float32); t85 = np.full(len(T), np.nan, np.float32)
for Yr in (2022, 2023, 2024, 2025):
    tr = (T < ts(Yr) - HOLD_S) & ~np.isnan(lab)
    te = (T >= ts(Yr)) & (T < (ts(Yr + 1) if Yr < 2025 else ts(2027)))
    ref = (T >= ts(Yr - 1)) & (T < ts(Yr) - HOLD_S)
    ms = [lgb.LGBMRegressor(**P, verbose=-1, n_jobs=4, random_state=s).fit(X[tr], np.nan_to_num(lab[tr]).clip(-1.2, 6.0)) for s in range(3)]
    sc_te = sum(m.predict(X[te]) for m in ms) / 3; sc_ref = sum(m.predict(X[ref]) for m in ms) / 3
    sc_all[te] = sc_te; t95[te] = np.quantile(sc_ref, 0.95); t85[te] = np.quantile(sc_ref, 0.85)
    print(Yr, flush=True)
np.savez(f"{D}/zm_sel.npz", sc=sc_all, t95=t95, t85=t85)
print("done", flush=True)
