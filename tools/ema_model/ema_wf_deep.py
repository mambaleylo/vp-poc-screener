"""EMA round 4: the yearly walk-forward retrained on longs with the v0.99.664 rule's label (ema_lab_deep.py), same LightGBM
params as er_wf_long.py, 2 seeds. MODE ev: every long touch, 0 when the deep limit does not fill; MODE fill: only the
touches that filled -> er_sc_long_deep_<MODE>.npz"""
import sys
MODE = sys.argv[1]
import numpy as np, pandas as pd, lightgbm as lgb
from mk import ts
from common import D
import pyarrow.parquet as pq
names = pq.ParquetFile(f"{D}/er_all.parquet").schema.names
META = {"sym", "t", "j", "tf_s", "n_i", "lv"}
F = [c for c in names if c not in META and c.split("_")[0] not in ("E", "F")]
d = pd.read_parquet(f"{D}/er_all.parquet", columns=["t"] + [c for c in F if c != "t"])
X = d[F].values.astype(np.float32); T = d.t.values; Lg = d.side.values > 0
z = np.load(f"{D}/er_lab_deep.npz"); y = z["y"]
use = Lg & ~np.isnan(y)
if MODE == "fill": use &= y != 0
y = np.nan_to_num(y, nan=0.0).clip(-1.5, 6.0)
out = {}
for Y in (2022, 2023, 2024, 2025):
    tr = (T < ts(Y) - 21 * 86400) & use
    sc = np.full(len(T), np.nan); acc = np.zeros(Lg.sum())
    for s_ in range(2):
        acc += lgb.LGBMRegressor(n_estimators=500, learning_rate=0.02, num_leaves=15, min_child_samples=1000 if MODE == "ev" else 300, subsample=0.7,
                                 subsample_freq=1, colsample_bytree=0.6, reg_lambda=5.0, verbose=-1, n_jobs=2, random_state=s_).fit(X[tr], y[tr]).predict(X[Lg]) / 2
    sc[Lg] = acc; out[str(Y)] = sc
    print(MODE, Y, flush=True)
np.savez(f"{D}/er_sc_long_deep_{MODE}.npz", **out)
print("done", flush=True)
