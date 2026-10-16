"""walk-forward scores per label saved (2022..2025); replays with the fill filter, thresholds and the cap"""
import os, sys, json
LABS = sys.argv[1:]
import numpy as np, pandas as pd, lightgbm as lgb
from mk import ts
from common import D
import pyarrow.parquet as pq
names = pq.ParquetFile(f"{D}/er_all.parquet").schema.names
META = ["sym", "t", "j", "tf_s", "n_i", "lv"]
F = [c for c in names if c not in META and c.split("_")[0] not in ("E", "F")]
cols = META + F + [c for l in LABS for c in (l, l + "_h")]
d = pd.read_parquet(f"{D}/er_all.parquet", columns=cols)
d["pen"] = pd.read_parquet(f"{D}/er_pen.parquet").pen.values
X = d[F].values.astype(np.float32); T = d.t.values
from er_wf import replay, summ
for lab in LABS:
    fn = f"{D}/er_sc_{lab}.npz"
    if not os.path.exists(fn):
        y = np.nan_to_num(d[lab].values, nan=0.0).clip(-1.5, 6.0)
        S = {}
        for Y in (2022, 2023, 2024, 2025):
            tr = T < ts(Y) - 21 * 86400
            sc = np.zeros(len(T), dtype=np.float32)
            for s_ in range(2):
                sc += lgb.LGBMRegressor(n_estimators=500, learning_rate=0.02, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1,
                                        colsample_bytree=0.6, reg_lambda=5.0, verbose=-1, n_jobs=4, random_state=s_).fit(X[tr], y[tr]).predict(X) / 2
            S[str(Y)] = sc
        np.savez(fn, **S)
    S = np.load(fn)
    for pen in (0.0, 0.1, 0.2):
        for q in (0.95, 0.97, 0.98):
            line = []
            for Y in (2022, 2023, 2024, 2025):
                sc = S[str(Y)]
                ref = (T >= ts(Y - 1)) & (T < ts(Y) - 21 * 86400)
                thr = float(np.quantile(sc[ref], q))
                te = (T >= ts(Y)) & (T < (ts(Y + 1) if Y < 2025 else ts(2027))) & (d.pen.values >= pen)
                sub = d[te].reset_index(drop=True)
                wk = ((ts(Y + 1) if Y < 2025 else ts(2026, 10)) - ts(Y)) / (7 * 86400)
                s = summ(replay(sub, sc[te], thr, lab, 12), wk)
                line.append(f"{Y}: {s['avg']:+.2f}R×{s['wk']}/нед Σ{s['sum']:.0f} dd{s['dd']:.0f}")
            print(f"{lab:14s} pen≥{pen} top{100 - q * 100:.0f}%: " + " | ".join(line), flush=True)
