"""Peak Reversal v3 (the adaptation study, ad_wf.py): the same rule (stop 1.5 ATR, take 3R, 48 bars, top 1% per side),
the model trained on the LAST 24 MONTHS only and retrained every quarter. The yearly stats = that scheme's
walk-forward (3 models per retrain, per quarter, 2023-01 .. 2026-09); the export = 3 models per side on the last 24
months, the threshold from the last 12 months' scores."""
import os, json, datetime as dt
SK, TK, Q, WIN, STEP = 1.5, 3.0, 0.99, 24, 3
import numpy as np, lightgbm as lgb
from mk import ts
from lgbpure import export
import prv_wf as W
def month_add(t, k):
    d = dt.datetime.fromtimestamp(int(t), dt.timezone.utc)
    m = d.month - 1 + k
    return int(dt.datetime(d.year + m // 12, m % 12 + 1, 1, tzinfo=dt.timezone.utc).timestamp())
lab = W.lab_of(SK, TK)
GAP = 10 * 86400
def mdl(seed):
    return lgb.LGBMRegressor(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1,
                             colsample_bytree=0.5, reg_lambda=10.0, verbose=-1, n_jobs=4, random_state=seed)
def fit3(tr_mask, s):
    ok = tr_mask & (W.SD == s) & ~np.isnan(lab)
    return [mdl(seed).fit(W.X[ok], lab[ok].clip(-1.5, TK + 1)) for seed in range(3)]
def score(ms, idx):
    return sum(m.predict(W.X[idx]) for m in ms) / len(ms)
if os.environ.get("WF", "1") == "1":
    sel = []
    t0, end = ts(2023), ts(2026, 10)
    while t0 < end:
        t1 = min(month_add(t0, STEP), end)
        tr = (W.T < t0 - GAP) & (W.T >= month_add(t0, -WIN) - GAP)
        ref = (W.T >= month_add(t0, -12) - GAP) & (W.T < t0 - GAP)
        te = (W.T >= t0) & (W.T < t1)
        for s in (1, -1):
            ms = fit3(tr, s)
            ri, ti = np.where(ref & (W.SD == s))[0], np.where(te & (W.SD == s))[0]
            thr = float(np.quantile(score(ms, ri), Q))
            sel.append(ti[score(ms, ti) >= thr])
        print("quarter", dt.datetime.fromtimestamp(t0, dt.timezone.utc).strftime("%Y-%m"), flush=True)
        t0 = t1
    out = sorted(W.replay(np.concatenate(sel), lab))
    years = {}
    for y in (2023, 2024, 2025):
        rs = np.array([r for e, r in out if (ts(y) <= e < ts(y + 1)) or (y == 2025 and e >= ts(2026))])
        c = np.cumsum(rs); dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], c])) - np.concatenate([[0], c])))
        years[str(y)] = {"n": len(rs), "avg": round(float(rs.mean()), 3), "wk": round(len(rs) / W.wk(y), 1), "sum": round(float(rs.sum()), 1),
                         "dd": round(dd, 1), "wr": round(float((rs > 0).mean() * 100), 1)}
        print(y, years[str(y)], flush=True)
    json.dump(years, open(f"{W.D}/prv3_years.json", "w"))
years = json.load(open(f"{W.D}/prv3_years.json"))
tmax = int(W.T.max())
full = (W.T < tmax - GAP) & (W.T >= month_add(tmax, -WIN) - GAP)
last = W.T >= tmax - 365 * 86400
models, thr = {}, {}
for s in (1, -1):
    ms = fit3(full, s)
    models[str(s)] = [export(m.booster_, W.NAMES)["trees"] for m in ms]
    w = np.where(last & (W.SD == s))[0]
    thr[str(s)] = round(float(np.quantile(score(ms, w), Q)), 6)
    print("side", s, "thr", thr[str(s)], flush=True)
out = {"ver": 2, "kind": "prv_v3", "feats": W.NAMES, "models": models, "thr": thr, "q": Q, "basis": ["EMA", 20], "band": 1.5,
       "rule": {"stop_atr": SK, "take_r": TK, "hold_bars": 48}, "side_cap": 12, "trained_to": tmax,
       "train": {"window_months": WIN, "retrain_months": STEP, "from": int(month_add(tmax, -WIN))},
       "research": {"coins": 127, "cap": 12, "q": Q, "years": years, "scheme": "окно 24 мес, переобучение раз в 3 мес"}}
json.dump(out, open(f"{W.D}/vp_prv_model.json", "w"), separators=(",", ":"))
print("KB", os.path.getsize(f"{W.D}/vp_prv_model.json") // 1024, flush=True)
