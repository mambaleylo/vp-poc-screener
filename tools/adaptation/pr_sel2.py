"""v0.99.670 (more P/R trades): pr_sel.py + the thresholds at q 0.97 / 0.975 / 0.98 / 0.985 / 0.99 / 0.995 and the quarterly
models (pickled, to score new coins). Was: save the P/R walk-forward scores once (24 months, quarterly, 3 seeds; the deployed scheme) for every test event
2023-01 .. 2026-09 and the per-quarter thresholds at q 0.99 / 0.95 — filter hypotheses then need no retraining."""
import numpy as np, lightgbm as lgb, datetime as dt, pickle
from mk import ts
import prv_wf as W
SK, TK, WIN, STEP, GAP = 1.5, 3.0, 24, 3, 10 * 86400
lab = W.lab_of(SK, TK)
def month_add(t, k):
    d = dt.datetime.fromtimestamp(int(t), dt.timezone.utc); m = d.month - 1 + k
    return int(dt.datetime(d.year + m // 12, m % 12 + 1, 1, tzinfo=dt.timezone.utc).timestamp())
def mdl(seed):
    return lgb.LGBMRegressor(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1,
                             colsample_bytree=0.5, reg_lambda=10.0, verbose=-1, n_jobs=4, random_state=seed)
QS = (0.95, 0.97, 0.975, 0.98, 0.985, 0.99, 0.995)
idx, sco, thr, models = [], [], {q: [] for q in QS}, []
t0, end = ts(2023), ts(2026, 10)
while t0 < end:
    t1 = min(month_add(t0, STEP), end)
    tr = (W.T < t0 - GAP) & (W.T >= month_add(t0, -WIN) - GAP)
    ref = (W.T >= month_add(t0, -12) - GAP) & (W.T < t0 - GAP)
    te = (W.T >= t0) & (W.T < t1)
    for s in (1, -1):
        ok = tr & (W.SD == s) & ~np.isnan(lab)
        ms = [mdl(seed).fit(W.X[ok], lab[ok].clip(-1.5, TK + 1)) for seed in range(3)]
        ri, ti = np.where(ref & (W.SD == s))[0], np.where(te & (W.SD == s))[0]
        rs = sum(m.predict(W.X[ri]) for m in ms) / 3
        sc = sum(m.predict(W.X[ti]) for m in ms) / 3
        idx.append(ti); sco.append(sc)
        for q in QS: thr[q].append(np.full(len(ti), np.quantile(rs, q)))
        models.append((t0, t1, s, [m.booster_ for m in ms], {q: float(np.quantile(rs, q)) for q in QS}))
    print("quarter", dt.datetime.fromtimestamp(t0, dt.timezone.utc).strftime("%Y-%m"), flush=True)
    t0 = t1
np.savez(f"{W.D}/prv_sel2.npz", idx=np.concatenate(idx), sc=np.concatenate(sco), **{f"t{int(round(q * 1000))}": np.concatenate(thr[q]) for q in QS})
pickle.dump(models, open(f"{W.D}/prv_models_q.pkl", "wb"))
print("done", flush=True)
