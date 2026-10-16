import json, os, numpy as np, pandas as pd, lightgbm as lgb
from mk import ts
from common import D
from lgbpure import export
from er_wf import replay, summ
import pyarrow.parquet as pq
LAB, Q, PEN = "F_0.5_2.0_1", 0.97, 0.1
names = pq.ParquetFile(f"{D}/er_all.parquet").schema.names
META = ["sym", "t", "j", "tf_s", "n_i", "lv"]
F = [c for c in names if c not in META and c.split("_")[0] not in ("E", "F")]
d = pd.read_parquet(f"{D}/er_all.parquet", columns=META + F + [LAB, LAB + "_h"])
d["pen"] = pd.read_parquet(f"{D}/er_pen.parquet").pen.values
X = d[F].values.astype(np.float32); T = d.t.values
S = np.load(f"{D}/er_sc_{LAB}.npz")
years = {}
for Y in (2022, 2023, 2024, 2025):
    sc = S[str(Y)]
    ref = (T >= ts(Y - 1)) & (T < ts(Y) - 21 * 86400)
    thr = float(np.quantile(sc[ref], Q))
    te = (T >= ts(Y)) & (T < (ts(Y + 1) if Y < 2025 else ts(2027))) & (d.pen.values >= PEN)
    sub = d[te].reset_index(drop=True)
    wk = ((ts(Y + 1) if Y < 2025 else ts(2026, 10)) - ts(Y)) / (7 * 86400)
    out = replay(sub, sc[te], thr, LAB, 12)
    s = summ(out, wk)
    rs = np.array([r for _, r in out])
    s["wr"] = round(float((rs > 0).mean() * 100), 1) if len(rs) else None
    years[str(Y)] = s
print(json.dumps(years))
y = np.nan_to_num(d[LAB].values, nan=0.0).clip(-1.5, 6.0)
full = T < T.max() - 2 * 86400
models, sc = [], np.zeros(len(T))
for s_ in range(3):
    m = lgb.LGBMRegressor(n_estimators=500, learning_rate=0.02, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1,
                          colsample_bytree=0.6, reg_lambda=5.0, verbose=-1, n_jobs=4, random_state=s_).fit(X[full], y[full])
    models.append(export(m.booster_, F)["trees"])
    sc += m.predict(X) / 3
last = T >= T.max() - 365 * 86400
thr = float(np.quantile(sc[last], Q))
out = {"ver": 1, "kind": "ema_touch", "feats": F, "models": models, "thr": round(thr, 6), "q": Q, "lab": LAB,
       "rule": {"stop_datr": 0.5, "take_r": 2.0, "hold_h": 24}, "side_cap": 12, "trained_to": int(T.max()),
       "research": {"coins": 127, "cap": 12, "q": Q, "years": years}}
json.dump(out, open(f"{D}/vp_ema_model.json", "w"), separators=(",", ":"))
print("thr", thr, "KB", os.path.getsize(f"{D}/vp_ema_model.json") // 1024)
