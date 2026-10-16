"""what to expect from the strong zones: the walk-forward trades (q 0.95, cap 12) month by month"""
import json
LAB = "G_1.0_R3.0"
import lightgbm as lgb
from mk import *
d = df([LAB]); F = feats(d); X = d[F].values.astype(np.float32); T = d.t.values
tm = pd.read_parquet(f"{D}/times.parquet")
d["f1"], d["ex"] = tm.f1.values, tm.ex.values
y = np.nan_to_num(d[LAB].values, nan=0.0).clip(-1.2, 6.0)
trades = []
for Y in (2022, 2023, 2024, 2025):
    tr = T < ts(Y) - HOLD_S
    sc = np.zeros(len(T))
    for s_ in range(3):
        sc += lgb.LGBMRegressor(n_estimators=500, learning_rate=0.02, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1,
                                colsample_bytree=0.6, reg_lambda=5.0, verbose=-1, n_jobs=4, random_state=s_).fit(X[tr], y[tr]).predict(X) / 3
    ref = (T >= ts(Y - 1)) & (T < ts(Y) - HOLD_S)
    te = (T >= ts(Y)) & (T < (ts(Y + 1) if Y < 2025 else ts(2027)))
    thr = float(np.quantile(sc[ref], 0.95))
    s = d.loc[te & (sc >= thr), ["t", "sym", "side_s", LAB, "f1", "ex"]].copy()
    s["sc"] = sc[te & (sc >= thr)]
    s = s.sort_values(["t", "sc"], ascending=[True, False])
    busy, act = {}, []
    for t, sym, side, r, f1, ex, sc_ in s.itertuples(index=False):
        if busy.get((sym, side), 0) > t:
            continue
        end = t + (ex + 1) * 3600 if ex == ex else t + HOLD_S
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == side) >= 12:
            continue
        busy[(sym, side)] = end
        act.append((end, side))
        trades.append({"y": Y, "t": int(t), "end": int(end), "fill": None if f1 != f1 else int(f1), "sym": sym, "side": side,
                       "r": None if r != r else round(float(r), 3)})
    print(Y, "done", flush=True)
json.dump(trades, open(f"{D}/zm_expect.json", "w"))
