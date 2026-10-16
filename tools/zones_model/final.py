"""The chosen rule: walk-forward check per year incl. the unseen 2025–26 (universe = top-N by volume, like the
bot), then the final model on all data, exported for the phone."""
import os, sys, json
LAB = os.environ.get("LAB", "G_1.0_R3.0")
Q = float(os.environ.get("Q", 0.98))
SEEDS = int(os.environ.get("SEEDS", 3))
import lightgbm as lgb
from mk import *
from lgbpure import export
d = df([LAB, LAB + "_h"]); F = feats(d); X = d[F].values.astype(np.float32); T = d.t.values
y = np.nan_to_num(d[LAB].values, nan=0.0).clip(-1.2, 6.0)
R = pd.read_pickle(f"{D}/volrank.pkl")
rt = R.index.values + 86400
k = np.searchsorted(rt, T, side="right") - 1
rank = np.full(len(T), 999.0)
ok = k >= 0
cols = {c: i for i, c in enumerate(R.columns)}
ci = np.array([cols.get(s, -1) for s in d.sym.values])
RV = R.values
rank[ok] = np.where(ci[ok] >= 0, RV[k[ok], np.maximum(ci[ok], 0)], 999)
rank = np.nan_to_num(rank, nan=999)
def mdl(seed):
    return lgb.LGBMRegressor(n_estimators=500, learning_rate=0.02, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1,
                             colsample_bytree=0.6, reg_lambda=5.0, verbose=-1, n_jobs=4, random_state=seed)
busy_h = None
summary = {"lab": LAB, "q": Q, "years": {}}
for Y in ((2022, 2023, 2024, 2025) if os.environ.get("FOLDS", "1") == "1" else ()):
    tr = T < ts(Y) - HOLD_S
    te_end = ts(Y + 1) if Y < 2025 else ts(2027)
    sc = np.zeros(len(T))
    for s_ in range(SEEDS):
        sc += mdl(s_).fit(X[tr], y[tr]).predict(X) / SEEDS
    ref = (T >= ts(Y - 1)) & (T < ts(Y) - HOLD_S)
    thr = float(np.quantile(sc[ref], Q))
    row = {}
    for uni in (40, 80, 120, 999):
        te = (T >= ts(Y)) & (T < te_end) & (rank <= uni)
        sub = d[te].reset_index(drop=True)
        trd = replay(sub, sc[te], thr, LAB, hcol=LAB + "_h")
        t1 = ts(Y + 1) if Y < 2025 else ts(2026, 10)
        s = st(trd, ts(Y), t1)
        f = trd.r.dropna()
        if len(f):
            cum = f.cumsum().values
            s["dd"] = round(float(np.max(np.maximum.accumulate(np.concatenate([[0], cum])) - np.concatenate([[0], cum]))), 1)
            ls = mx = 0
            for v in f.values:
                ls = ls + 1 if v < 0 else 0
                mx = max(mx, ls)
            s["max_ls"] = mx
            s["days"] = round(float(trd.h.dropna().mean()) / 24, 1)
        row[uni] = s
    summary["years"][Y] = row
    print(Y, json.dumps(row), flush=True)
if summary["years"]:
    json.dump(summary, open(f"{D}/final_{LAB}_{Q}.json", "w"))
else:
    summary = json.load(open(f"{D}/final_{LAB}_{Q}.json"))
if os.environ.get("EXPORT") == "1":
    full = T < T.max() - HOLD_S
    models = []
    sc = np.zeros(len(T))
    for s_ in range(SEEDS):
        m = mdl(s_).fit(X[full], y[full])
        models.append(export(m.booster_, F)["trees"])
        sc += m.predict(X) / SEEDS
    last = T >= T.max() - 365 * 86400
    thr = float(np.quantile(sc[last], Q))
    bk, tk = LAB.split("_")[1], LAB.split("_")[2]
    out = {"ver": 1, "rule": {"buf_datr": float(bk), "tp_r": float(tk[1:])}, "feats": F, "models": models, "thr": round(thr, 6), "q": Q, "lab": LAB, "trained_to": int(T.max()),
           "research": summary}
    json.dump(out, open(f"{D}/vp_zones_model.json", "w"), separators=(",", ":"))
    print("exported, thr", thr, "size KB", os.path.getsize(f"{D}/vp_zones_model.json") // 1024)
