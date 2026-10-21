"""Neuro round 4 (nx_sel_lim.py): retrained on the v0.99.663 rule's label (nx_lab_lim.py: the limit 0.3 ATR / 3 h, stop 1 ATR,
take 3R, 12 h; 0 when it does not fill). Otherwise = nx_sel.py. Was: the deployed scheme's walk-forward scores saved once (all history before each year, retrained yearly, per side,
3 seeds; the label stop 1 ATR / take 3R / 48 h), for every hour 2022 .. 2026-09 and both sides, + the thresholds
(q 0.995 = the bot, q 0.98 = a check set) from the year before -> nx_sel.npz"""
import sys, numpy as np, lightgbm as lgb, glob
from common import D
from mk import ts
import nx_feat
Xs, Ys, Ts, Ss = [], [], [], []
for k, fn in enumerate(sorted(glob.glob(f"{D}/nx/*.npz"))):
    z = np.load(fn)
    if not len(z["t"]): continue
    Xs.append(z["X"]); Ys.append(np.load(fn.replace("/nx/", "/nxl/"))["Y"]); Ts.append(z["t"]); Ss.append(np.full(len(z["t"]), k, np.int16))
X = np.concatenate(Xs); Y = np.concatenate(Ys); T = np.concatenate(Ts); SY = np.concatenate(Ss)
ok = X[:, nx_feat.NAMES.index("atr_pct")] >= 0.1
X, Y, T, SY = X[ok], Y[ok], T[ok], SY[ok]
Y = np.where(np.abs(Y) > 20, np.nan, Y)
P = dict(n_estimators=300, learning_rate=0.04, num_leaves=31, min_child_samples=2000, subsample=0.5, subsample_freq=1, colsample_bytree=0.5, reg_lambda=10.0)
out = {"T": T, "SY": SY, "keep": np.where(ok)[0]}
for si, s in ((0, 1), (1, -1)):
    lab = Y[:, si].astype(float)
    sc_all = np.full(len(T), np.nan, dtype=np.float32); t99, t98 = np.full(len(T), np.nan, np.float32), np.full(len(T), np.nan, np.float32)
    for Yr in (2022, 2023, 2024, 2025):
        tr = (T < ts(Yr) - 3 * 86400) & ~np.isnan(lab)
        te = (T >= ts(Yr)) & (T < (ts(Yr + 1) if Yr < 2025 else ts(2027)))
        ref = (T >= ts(Yr - 1)) & (T < ts(Yr) - 3 * 86400)
        ms = [lgb.LGBMRegressor(**P, verbose=-1, n_jobs=2, random_state=seed).fit(X[tr], lab[tr].clip(-1.5, 4.0)) for seed in range(3)]
        sc_te = sum(m.predict(X[te]) for m in ms) / 3; sc_ref = sum(m.predict(X[ref]) for m in ms) / 3
        sc_all[te] = sc_te; t99[te] = np.quantile(sc_ref, 0.995); t98[te] = np.quantile(sc_ref, 0.98)
        print("side", s, Yr, flush=True)
    out[f"sc{s}"] = sc_all; out[f"t995_{s}"] = t99; out[f"t98_{s}"] = t98
np.savez(f"{D}/nx_sel_lim.npz", **out)
print("done", flush=True)
