import os, sys
LABS = sys.argv[1:]
LABS = sys.argv[1:]
import lightgbm as lgb
from mk import *
d = df(LABS); F = feats(d); X = d[F].values.astype(np.float32); T = d.t.values

for lab in LABS:
    y = np.nan_to_num(d[lab].values, nan=0.0).clip(-1.2, 6.0)
    hcol = lab + "_h"
    res = {q: [] for q in (0.95, 0.98, 0.99)}
    for Y in (2022, 2023, 2024):
        tr = T < ts(Y) - HOLD_S
        te = (T >= ts(Y)) & (T < ts(Y + 1))
        sc = np.zeros(len(T))
        for seed in range(2):
            sc += lgb.LGBMRegressor(n_estimators=500, learning_rate=0.02, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1,
                                    colsample_bytree=0.6, reg_lambda=5.0, verbose=-1, n_jobs=4, random_state=seed).fit(X[tr], y[tr]).predict(X)
        ref = (T >= ts(Y - 1)) & (T < ts(Y) - HOLD_S)
        for q in res:
            thr = float(np.quantile(sc[ref], q))
            tr_ = replay(d[te].reset_index(drop=True), sc[te], thr, lab)
            s = st(tr_, ts(Y), ts(Y + 1))
            # mean days held of the filled trades
            sel = d[te].reset_index(drop=True)
            res[q].append((s.get("n", 0), s.get("avg") or 0))
    out = []
    for q, v in res.items():
        n = sum(a for a, _ in v)
        avg = sum(a * b for a, b in v) / n if n else 0
        out.append(f"top{100 - q * 100:.0f}%: " + " ".join(f"{b:+.2f}({a})" for a, b in v) + f" → {avg:+.3f}")
    print(f"{lab:18s} " + " | ".join(out), flush=True)
