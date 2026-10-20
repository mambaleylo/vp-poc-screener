"""EMA cascade (EMA 5/10/14/20/28, 1h): the model the bot runs. 3 models per side (seeds 0-2) on every event so far,
the label = stop at the 24-bar swing extreme ±0.2 ATR, take 2R, out after 48 bars; the threshold = the top 0.5% of the
last 12 months' scores per side. The research stats = the yearly walk-forward (cas_sel.py, q 0.995, cap 12)."""
import os, json
import numpy as np, lightgbm as lgb
from lgbpure import export
from common import D
import nx_feat
Q = 0.995
CN = ["rng", "prior", "since_opp", "exc", "move24", "width", "b24", "atrp"]
NAMES = CN + nx_feat.NAMES
z = np.load(f"{D}/cas_all.npz"); X, Y, T = z["X"], z["Y"], z["T"]; SD = X[:, 0].astype(int)
lab = Y[:, 3, 1, 1]          # sw, t2, 48
tmax = int(T.max()); last = T >= tmax - 365 * 86400
def mdl(seed):
    return lgb.LGBMRegressor(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1,
                             colsample_bytree=0.5, reg_lambda=10.0, verbose=-1, n_jobs=4, random_state=seed)
models, thr = {}, {}
for s in (1, -1):
    ok = np.where((SD == s) & ~np.isnan(lab))[0]
    if len(ok) > 400000: ok = np.random.default_rng(1).choice(ok, 400000, replace=False)
    ms = [mdl(seed).fit(X[ok, 1:], lab[ok].clip(-1.5, 4)) for seed in range(3)]
    models[str(s)] = [export(m.booster_, NAMES)["trees"] for m in ms]
    w = np.where(last & (SD == s))[0]
    sc = sum(m.predict(X[w, 1:]) for m in ms) / 3
    thr[str(s)] = round(float(np.quantile(sc, Q)), 6)
    print("side", s, "thr", thr[str(s)], flush=True)
years = json.load(open(f"{D}/cas_years.json"))
out = {"ver": 1, "kind": "cas_v1", "feats": NAMES, "models": models, "thr": thr, "q": Q, "emas": [5, 10, 14, 20, 28],
       "rule": {"swing_bars": 24, "swing_pad_atr": 0.2, "take_r": 2.0, "hold_bars": 48, "min_risk_pct": 0.2}, "side_cap": 12, "trained_to": tmax,
       "research": {"coins": 127, "cap": 12, "q": Q, "years": years, "scheme": "годовой walk-forward, обучение на всей истории до года"}}
json.dump(out, open(f"{D}/vp_cas_model.json", "w"), separators=(",", ":"))
print("KB", os.path.getsize(f"{D}/vp_cas_model.json") // 1024, flush=True)
