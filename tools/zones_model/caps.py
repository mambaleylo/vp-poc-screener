"""portfolio replay with exact times and a cap on active zones per side; equity by exit time"""
import json
LAB = "G_1.0_R3.0"
import lightgbm as lgb
from mk import *
d = df([LAB]); F = feats(d); X = d[F].values.astype(np.float32); T = d.t.values
tm = pd.read_parquet(f"{D}/times.parquet")
d["f1"], d["ex"] = tm.f1.values, tm.ex.values
y = np.nan_to_num(d[LAB].values, nan=0.0).clip(-1.2, 6.0)

def rep(sub, sc, thr, cap):
    m = sc >= thr
    s = sub.loc[m, ["t", "sym", "side_s", LAB, "f1", "ex"]].copy()
    s["sc"] = sc[m]
    s = s.sort_values(["t", "sc"], ascending=[True, False])
    busy, act, out = {}, [], []
    for t, sym, side, r, f1, ex, sc_ in s.itertuples(index=False):
        if busy.get((sym, side), 0) > t:
            continue
        end = t + (ex + 1) * 3600 if ex == ex else t + HOLD_S
        act = [a for a in act if a[0] > t]
        if cap and sum(1 for a in act if a[1] == side) >= cap:
            continue
        busy[(sym, side)] = end
        act.append((end, side))
        if r == r:
            out.append((end, r))
    return out

def summ(out):
    if not out:
        return {"n": 0}
    out.sort()
    rs = np.array([r for _, r in out]); cum = np.cumsum(rs)
    dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], cum])) - np.concatenate([[0], cum])))
    return {"n": len(rs), "avg": round(float(rs.mean()), 3), "sum": round(float(rs.sum()), 1), "dd": round(dd, 1), "ratio": round(float(rs.sum()) / dd, 2) if dd else None}

res = {}
for Y in (2022, 2023, 2024, 2025):
    tr = T < ts(Y) - HOLD_S
    sc = np.zeros(len(T))
    for s_ in range(3):
        sc += lgb.LGBMRegressor(n_estimators=500, learning_rate=0.02, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1,
                                colsample_bytree=0.6, reg_lambda=5.0, verbose=-1, n_jobs=4, random_state=s_).fit(X[tr], y[tr]).predict(X) / 3
    ref = (T >= ts(Y - 1)) & (T < ts(Y) - HOLD_S)
    te = (T >= ts(Y)) & (T < (ts(Y + 1) if Y < 2025 else ts(2027)))
    sub = d[te].reset_index(drop=True)
    wk = ((ts(Y + 1) if Y < 2025 else ts(2026, 10)) - ts(Y)) / (7 * 86400)
    for q in (0.95, 0.97, 0.98):
        thr = float(np.quantile(sc[ref], q))
        for cap in (0, 12, 8, 5, 3):
            s = summ(rep(sub, sc[te], thr, cap))
            s["wk"] = round(s["n"] / wk, 1)
            res.setdefault(f"{q}/{cap}", {})[Y] = s
    print(Y, "done", flush=True)
for k, v in res.items():
    print(f"q={k:7s} " + " | ".join(f"{Y}: {s.get('avg')}R×{s.get('wk')}/wk sum={s.get('sum')} dd={s.get('dd')}" for Y, s in v.items()))
json.dump(res, open(f"{D}/caps.json", "w"))
