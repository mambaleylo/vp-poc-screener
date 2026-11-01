"""EMA reproducibility (the audit): retrain the deployed recipe (er_export2.py EXPORT: 3 LightGBM seeds, label F_0.75_4.0_3
clipped, every touch older than T.max - hold - 1 day) on the touches rebuilt from scratch (dl.py 1h -> er_build -> er_df ->
er_lab3 -> er_pen), then compare with vp_ema_model.json: the same touch count / last touch, the trees, the scores, the top 4%
picks and their R."""
import json, numpy as np, pandas as pd, lightgbm as lgb
from common import D
from lgbpure import export, predict
m0 = json.load(open("/home/user/vp-poc-screener/vp_ema_model.json"))
LAB, F = m0["lab"], m0["feats"]; TAKE, HOLD = 4.0, 3.0
d = pd.read_parquet(f"{D}/er_all.parquet", columns=["sym", "t", "side", "tf_s"] + [c for c in F if c not in ("side",)] + [LAB])
pen = pd.read_parquet(f"{D}/er_pen.parquet").pen.values
T = d.t.values; X = d[F].values.astype(np.float64)
print(f"касаний {len(d)}, последнее {pd.to_datetime(T.max(), unit='s')} (у бота trained_to {pd.to_datetime(m0['trained_to'], unit='s')})", flush=True)
y = np.nan_to_num(d[LAB].values, nan=0.0).clip(-1.5, TAKE + 1)
full = T < m0["trained_to"] - HOLD * 86400 - 86400
models, sc = [], np.zeros(len(T))
for s_ in range(3):
    m = lgb.LGBMRegressor(n_estimators=500, learning_rate=0.02, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1,
                          colsample_bytree=0.6, reg_lambda=5.0, verbose=-1, n_jobs=4, random_state=s_).fit(X[full], y[full])
    models.append(export(m.booster_, F)["trees"]); sc += m.predict(X) / 3
same = sum(json.dumps(a) == json.dumps(b) for a, b in zip(models, m0["models"]))
print(f"деревья совпали: {same}/3", flush=True)
rng = np.random.default_rng(1); smp = rng.choice(len(T), min(60000, len(T)), replace=False)
dep = np.array([np.mean([predict({"feats": F, "trees": t}, list(X[i])) for t in m0["models"]]) for i in smp])
new = sc[smp]
print(f"корреляция оценок {np.corrcoef(dep, new)[0, 1]:.4f}, макс. разница {np.abs(dep - new).max():.4f}", flush=True)
ok = np.isfinite(d[LAB].values[smp]) & (pen[smp] >= 0.1) & (d.side.values[smp] > 0) & (d.tf_s.values[smp] != "4h")
r = d[LAB].values[smp]
for q in (0.96, 0.9):
    a = dep > np.quantile(dep, q); b = new > np.quantile(new, q)
    print(f"верхние {100 - q * 100:.0f}%: общих {(a & b).sum() / a.sum() * 100:.0f}%; R лонгов 1d/1w/1M бот {np.nanmean(r[a & ok]):+.3f} ({(a & ok).sum()}) | пересборка {np.nanmean(r[b & ok]):+.3f} ({(b & ok).sum()})", flush=True)
print("ema repro done", flush=True)
