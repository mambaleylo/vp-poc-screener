"""EMA cascade: walk-forward scores saved once (folds 2022..2026, trained on everything before the fold - 10 days,
threshold from the previous 12 months), for a few labels"""
import sys, os
ARGS = sys.argv[1:]
import numpy as np, lightgbm as lgb
from mk import ts
from common import D
z = np.load(f"{D}/cas_all.npz"); X, Y, T = z["X"], z["Y"], z["T"]
SD = X[:, 0].astype(int)
STOPS = ("1", "1.5", "2", "sw"); EXITS = ("t1", "t2", "t3", "cas"); HOLDS = (24, 48)
LABS = ARGS or ["sw_t2_48", "sw_t1_48", "2_t3_48"]
FOLDS = (2022, 2023, 2024, 2025, 2026)
out = {"T": T}
for nm in LABS:
    a, b, c = nm.split("_"); lab = Y[:, STOPS.index(a), EXITS.index(b), HOLDS.index(int(c))]
    for s in (1, -1):
        sc = np.full(len(T), np.nan, np.float32)
        thr = {}
        for y in FOLDS:
            tr = T < ts(y) - 10 * 86400; te = (T >= ts(y)) & (T < ts(y + 1)); ref = (T >= ts(y - 1)) & (T < ts(y) - 10 * 86400)
            ok = np.where(tr & (SD == s) & ~np.isnan(lab))[0]
            if len(ok) > 400000: ok = np.random.default_rng(1).choice(ok, 400000, replace=False)
            m = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.03, min_child_samples=1000, subsample=0.7, subsample_freq=1,
                                  colsample_bytree=0.5, reg_lambda=10.0, verbose=-1, n_jobs=4, random_state=int(os.environ.get("SEED", 1)), num_leaves=int(os.environ.get("NL", 15))).fit(X[ok, 1:], lab[ok].clip(-1.5, 4))
            w = (SD == s) & (ref | te); p = m.predict(X[w, 1:])
            r = p[ref[w]]; sc[w & te] = p[te[w]]
            for q in (0.98, 0.99, 0.995): out[f"thr_{nm}_{s}_{q}_{y}"] = float(np.quantile(r, q))
            print(nm, s, y, flush=True)
        out[f"sc_{nm}_{s}"] = sc
np.savez(D + '/cas_sel_s' + os.environ.get('SEED', '1') + '_' + os.environ.get('NL', '15') + '.npz', **out)
