"""EMA: the yearly walk-forward retrained on LONG touches only (the deployed rule trades longs only), for a label;
scores of every long touch per year model -> er_sc_long_<LAB>.npz (NaN for shorts). Same params as er_wf.py, 2 seeds."""
import sys, numpy as np, pandas as pd, lightgbm as lgb
LABS = sys.argv[1:]
from mk import ts
from common import D
import pyarrow.parquet as pq
names = pq.ParquetFile(f"{D}/er_all.parquet").schema.names
META = {"sym", "t", "j", "tf_s", "n_i", "lv"}
F = [c for c in names if c not in META and c.split("_")[0] not in ("E", "F")]
d = pd.read_parquet(f"{D}/er_all.parquet", columns=list(META) + F + LABS)
X = d[F].values.astype(np.float32); T = d.t.values; L = d.side.values > 0
for lab in LABS:
    y = np.nan_to_num(d[lab].values, nan=0.0).clip(-1.5, 6.0)
    out = {}
    for Y in (2022, 2023, 2024, 2025):
        tr = (T < ts(Y) - 21 * 86400) & L
        sc = np.full(len(T), np.nan); acc = np.zeros(L.sum())
        for s_ in range(2):
            acc += lgb.LGBMRegressor(n_estimators=500, learning_rate=0.02, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1,
                                     colsample_bytree=0.6, reg_lambda=5.0, verbose=-1, n_jobs=4, random_state=s_).fit(X[tr], y[tr]).predict(X[L]) / 2
        sc[L] = acc; out[str(Y)] = sc
        print(lab, Y, flush=True)
    np.savez(f"{D}/er_sc_long_{lab}.npz", **out)
print("done", flush=True)
