"""EMA cascade: walk-forward variants of the model (label sw_t2_48). Env: TAG (output cas_sel_<TAG>.npz), STEP (months
per fold, 12 = yearly), WIN (training window in months, 0 = all history), SEEDS (models averaged), FEAT2 (the extra
context of cas_ev2.py), ONE (one model for both sides, the side a feature), NL (leaves), CLS (learn P(R>0) instead).
Stored: the scores and, per event, the threshold of its fold (q of the previous 12 months' scores)."""
import os, glob, datetime as dt
import numpy as np, lightgbm as lgb
from mk import ts
from common import D
E = lambda k, d: os.environ.get(k, d)
TAG, STEP, WIN, SEEDS, FEAT2, ONE, NL, CLS = E("TAG", "x"), int(E("STEP", 12)), int(E("WIN", 0)), int(E("SEEDS", 1)), E("FEAT2", "0") == "1", E("ONE", "0") == "1", int(E("NL", 15)), E("CLS", "0") == "1"
z = np.load(f"{D}/cas_all.npz"); X, Y, T = z["X"], z["Y"], z["T"]
SD = X[:, 0].astype(int)
if FEAT2:
    syms = [os.path.basename(f)[:-4] for f in sorted(glob.glob(f"{D}/cas/*.npz"))]
    F2 = []
    for sym in syms:
        Fe = np.load(f"{D}/cas/{sym}.npz")["F"]; f2 = np.load(f"{D}/cas2/{sym}.npz")["F2"]
        nf = np.load(f"{D}/nxf/{sym}.npz"); have = set(int(t) + 3600 for t in nf["t"])
        ok = np.array([int(t) in have for t in Fe[:, 0]])     # the same filter as cas_all
        F2.append(f2[ok])
    F2 = np.concatenate(F2); assert len(F2) == len(X)
    X = np.hstack([X, F2])
cols = slice(0, None) if ONE else slice(1, None)
lab = np.load(E("LAB", "")) if E("LAB", "") else Y[:, 3, 1, 1]   # LAB: another label (cas_lab_part.py)
def month_add(t, k):
    d = dt.datetime.fromtimestamp(int(t), dt.timezone.utc); m = d.month - 1 + k
    return int(dt.datetime(d.year + m // 12, m % 12 + 1, 1, tzinfo=dt.timezone.utc).timestamp())
def mdl(seed):
    kw = dict(n_estimators=300, learning_rate=0.03, num_leaves=NL, min_child_samples=1000, subsample=0.7, subsample_freq=1,
              colsample_bytree=0.5, reg_lambda=10.0, verbose=-1, n_jobs=4, random_state=seed)
    return lgb.LGBMClassifier(**kw) if CLS else lgb.LGBMRegressor(**kw)
def fit(idx):
    y = (lab[idx] > 0).astype(int) if CLS else lab[idx].clip(-1.5, 4 if not E("LAB", "") else 2)
    return [mdl(1 + k).fit(X[idx][:, cols], y) for k in range(SEEDS)]
def pred(ms, idx):
    return sum((m.predict_proba(X[idx][:, cols])[:, 1] if CLS else m.predict(X[idx][:, cols])) for m in ms) / len(ms)
out = {}
sc = {s: np.full(len(T), np.nan, np.float32) for s in (1, -1)}
thr = {(s, q): np.full(len(T), np.inf, np.float32) for s in (1, -1) for q in (0.98, 0.99, 0.995)}
t0, end = ts(2022), ts(2026, 11)
GAP = 10 * 86400
rng = np.random.default_rng(1)
while t0 < end:
    t1 = min(month_add(t0, STEP), end)
    tr = (T < t0 - GAP) & ((T >= month_add(t0, -WIN) - GAP) if WIN else True) & ~np.isnan(lab)
    ref = (T >= month_add(t0, -12) - GAP) & (T < t0 - GAP); te = (T >= t0) & (T < t1)
    groups = [(None, tr)] if ONE else [(s, tr & (SD == s)) for s in (1, -1)]
    for s, m in groups:
        ok = np.where(m)[0]
        if len(ok) > (800000 if ONE else 400000): ok = rng.choice(ok, 800000 if ONE else 400000, replace=False)
        ms = fit(ok)
        for side in ((1, -1) if ONE else (s,)):
            ri, ti = np.where(ref & (SD == side))[0], np.where(te & (SD == side))[0]
            if not len(ti) or not len(ri): continue
            pr = pred(ms, ri); sc[side][ti] = pred(ms, ti)
            for q in (0.98, 0.99, 0.995): thr[(side, q)][ti] = np.quantile(pr, q)
    print(TAG, dt.datetime.fromtimestamp(t0, dt.timezone.utc).strftime("%Y-%m"), flush=True)
    t0 = t1
for s in (1, -1):
    out[f"sc_sw_t2_48_{s}"] = sc[s]
    for q in (0.98, 0.99, 0.995): out[f"thrv_sw_t2_48_{s}_{q}"] = thr[(s, q)]
np.savez(f"{D}/cas_sel_{TAG}.npz", **out)
