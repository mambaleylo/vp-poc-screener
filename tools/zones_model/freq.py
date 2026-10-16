"""frequency vs quality: per-week trades and R per trade by threshold, every fold incl. 2025-26"""
import os, json
LAB = "G_1.0_R3.0"
import lightgbm as lgb
from mk import *
d = df([LAB, LAB + "_h"]); F = feats(d); X = d[F].values.astype(np.float32); T = d.t.values
y = np.nan_to_num(d[LAB].values, nan=0.0).clip(-1.2, 6.0)
QS = (0.80, 0.85, 0.90, 0.93, 0.95, 0.97, 0.98)
res = {}
for Y in (2022, 2023, 2024, 2025):
    tr = T < ts(Y) - HOLD_S
    sc = np.zeros(len(T))
    for s_ in range(3):
        sc += lgb.LGBMRegressor(n_estimators=500, learning_rate=0.02, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1,
                                colsample_bytree=0.6, reg_lambda=5.0, verbose=-1, n_jobs=4, random_state=s_).fit(X[tr], y[tr]).predict(X) / 3
    ref = (T >= ts(Y - 1)) & (T < ts(Y) - HOLD_S)
    te = (T >= ts(Y)) & (T < (ts(Y + 1) if Y < 2025 else ts(2027)))
    sub = d[te].reset_index(drop=True)
    for q in QS:
        thr = float(np.quantile(sc[ref], q))
        s = st(replay(sub, sc[te], thr, LAB), ts(Y), ts(Y + 1) if Y < 2025 else ts(2026, 10))
        res.setdefault(q, {})[Y] = s
        print(Y, q, s, flush=True)
json.dump({str(k): v for k, v in res.items()}, open(f"{D}/freq.json", "w"))
for q in QS:
    v = res[q]
    print(f"top{100 - q * 100:.0f}%: " + " | ".join(f"{Y}: {v[Y].get('avg')}R x {v[Y].get('wk')}/нед" for Y in v))
