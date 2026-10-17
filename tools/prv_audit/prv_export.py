"""Peak Reversal v2: the chosen rule (stop 1.5 ATR, take 3R, 48 bars, top q per side) — yearly walk-forward stats
(3 models per fold) and the export (3 models per side on all data) for the bot"""
import os, json
SK, TK, Q = 1.5, 3.0, float(os.environ.get("Q", 0.99))
import numpy as np, lightgbm as lgb
from mk import ts
from lgbpure import export
import prv_wf as W
lab = W.lab_of(SK, TK)
def mdl(seed):
    return lgb.LGBMRegressor(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1,
                             colsample_bytree=0.5, reg_lambda=10.0, verbose=-1, n_jobs=4, random_state=seed)
years = {}
for y in (2022, 2023, 2024, 2025):
    tr = W.T < ts(y) - 10 * 86400
    ref = (W.T >= ts(y - 1)) & (W.T < ts(y) - 10 * 86400)
    te = W.yr_mask(y)
    sc = np.full(len(W.T), -9.0)
    sel = []
    for s in (1, -1):
        ok = tr & (W.SD == s) & ~np.isnan(lab)
        w = (W.SD == s) & (ref | te)
        p = np.zeros(int(w.sum()))
        for seed in range(3):
            p += mdl(seed).fit(W.X[ok], lab[ok].clip(-1.5, TK + 1)).predict(W.X[w]) / 3
        sc[w] = p
        thr = float(np.quantile(sc[ref & (W.SD == s)], Q))
        sel.append(np.where(te & (W.SD == s) & (sc >= thr))[0])
    out = sorted(W.replay(np.concatenate(sel), lab))
    rs = np.array([r for _, r in out]); c = np.cumsum(rs)
    dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], c])) - np.concatenate([[0], c])))
    years[str(y)] = {"n": len(rs), "avg": round(float(rs.mean()), 3), "wk": round(len(rs) / W.wk(y), 1), "sum": round(float(rs.sum()), 1),
                     "dd": round(dd, 1), "wr": round(float((rs > 0).mean() * 100), 1)}
    print(y, years[str(y)], flush=True)
full = W.T < W.T.max() - 10 * 86400
last = W.T >= W.T.max() - 365 * 86400
models, thr = {}, {}
for s in (1, -1):
    ok = full & (W.SD == s) & ~np.isnan(lab)
    ms, sc = [], np.zeros(len(W.T))
    w = W.SD == s
    for seed in range(3):
        m = mdl(seed).fit(W.X[ok], lab[ok].clip(-1.5, TK + 1))
        ms.append(export(m.booster_, W.NAMES)["trees"])
        sc[w] += m.predict(W.X[w]) / 3
    models[str(s)] = ms
    thr[str(s)] = round(float(np.quantile(sc[last & w], Q)), 6)
    print("side", s, "thr", thr[str(s)], flush=True)
out = {"ver": 1, "kind": "prv_v2", "feats": W.NAMES, "models": models, "thr": thr, "q": Q, "basis": ["EMA", 20], "band": 1.5,
       "rule": {"stop_atr": SK, "take_r": TK, "hold_bars": 48}, "side_cap": 12, "trained_to": int(W.T.max()),
       "research": {"coins": 127, "cap": 12, "q": Q, "years": years}}
json.dump(out, open(f"{W.D}/vp_prv_model.json", "w"), separators=(",", ":"))
print("KB", os.path.getsize(f"{W.D}/vp_prv_model.json") // 1024, flush=True)
