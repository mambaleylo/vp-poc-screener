"""EMA: the far-take rule — yearly check (cap 12, fills >= 0.1% past the EMA), coin auto-selection re-tested on its
own trades, the per-coin tallies, and the export"""
import json, os, numpy as np, pandas as pd, lightgbm as lgb
from mk import ts
from common import D
from lgbpure import export
import pyarrow.parquet as pq
LAB, Q, PEN = os.environ.get("LAB", "F_0.75_4.0_3"), float(os.environ.get("Q", 0.97)), 0.1
STOP, TAKE, HOLD = (float(x) for x in LAB.split("_")[1:])
names = pq.ParquetFile(f"{D}/er_all.parquet").schema.names
META = ["sym", "t", "j", "tf_s", "n_i", "lv", "side"]
F = [c for c in names if c not in META[:-1] and c.split("_")[0] not in ("E", "F")]
d = pd.read_parquet(f"{D}/er_all.parquet", columns=list(dict.fromkeys(META + F + [LAB, LAB + "_h"])))
d["pen"] = pd.read_parquet(f"{D}/er_pen.parquet").pen.values
X = d[F].values.astype(np.float32); T = d.t.values
S = np.load(f"{D}/er_sc_{LAB}.npz")
def rep(sub, sc, thr):
    m = sc >= thr
    s = sub.loc[m, ["t", "sym", "side", LAB, LAB + "_h"]].copy(); s["sc"] = sc[m]
    s = s.sort_values(["t", "sc"], ascending=[True, False])
    busy, act, out = {}, [], []
    for t, sym, side, r, h, _ in s.itertuples(index=False):
        if busy.get((sym, side), 0) > t:
            continue
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == side) >= 12:
            continue
        end = t + int(h) * 3600
        busy[(sym, side)] = end; act.append((end, side))
        out.append((int(end), float(r), sym, int(side), int(t)))
    return out
def summ(rows, wk):
    rows = sorted(rows); rs = np.array([r[1] for r in rows])
    if not len(rs):
        return {"n": 0}
    cum = np.cumsum(rs); dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], cum])) - np.concatenate([[0], cum])))
    return {"n": len(rs), "avg": round(float(rs.mean()), 3), "wk": round(len(rs) / wk, 1), "sum": round(float(rs.sum()), 1), "dd": round(dd, 1),
            "wr": round(float((rs > 0).mean() * 100), 1)}
years, TR, WK = {}, {}, {}
for Y in (2022, 2023, 2024, 2025):
    sc = S[str(Y)]
    ref = (T >= ts(Y - 1)) & (T < ts(Y) - 21 * 86400)
    thr = float(np.quantile(sc[ref], Q))
    te = (T >= ts(Y)) & (T < (ts(Y + 1) if Y < 2025 else ts(2027))) & (d.pen.values >= PEN)
    sub = d[te].reset_index(drop=True)
    WK[Y] = ((ts(Y + 1) if Y < 2025 else ts(2026, 10)) - ts(Y)) / (7 * 86400)
    TR[Y] = rep(sub, sc[te], thr)
    years[str(Y)] = summ(TR[Y], WK[Y])
print("years", json.dumps(years), flush=True)
def base(s):
    b = s[:-4]
    return b[4:] if b.startswith("1000") else b
for name, mn, ma in (("all", None, None), ("past>=+0.1R n>=10", 10, 0.1), ("past>0 n>=10", 10, 0.0)):
    line = []
    for Y in (2023, 2024, 2025):
        tal = {}
        for yy in range(2022, Y):
            for e, r, sym, side, t in TR[yy]:
                n, s = tal.get(sym, (0, 0.0)); tal[sym] = (n + 1, s + r)
        rows = [x for x in TR[Y] if mn is None or (tal.get(x[2], (0, 0))[0] >= mn and tal[x[2]][1] / tal[x[2]][0] >= ma)]
        st = summ(rows, WK[Y]); line.append(f"{Y}: {st.get('avg', 0):+.2f}R×{st.get('wk', 0)}/нед Σ{st.get('sum', 0):.0f} dd{st.get('dd', 0):.0f}")
    print(f"coinsel {name:20s} " + " | ".join(line), flush=True)
coins = {}
for Y in TR:
    for e, r, sym, side, t in TR[Y]:
        n, s = coins.get(base(sym), (0, 0.0)); coins[base(sym)] = (n + 1, s + r)
json.dump({"years": years, "coins": {k: [v[0], round(v[1], 2)] for k, v in sorted(coins.items())}}, open(f"{D}/er_far_{LAB}.json", "w"))
if os.environ.get("EXPORT") == "1":
    y = np.nan_to_num(d[LAB].values, nan=0.0).clip(-1.5, TAKE + 1)
    full = T < T.max() - HOLD * 86400 - 86400
    models, sc = [], np.zeros(len(T))
    for s_ in range(3):
        m = lgb.LGBMRegressor(n_estimators=500, learning_rate=0.02, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1,
                              colsample_bytree=0.6, reg_lambda=5.0, verbose=-1, n_jobs=4, random_state=s_).fit(X[full], y[full])
        models.append(export(m.booster_, F)["trees"])
        sc += m.predict(X) / 3
    last = T >= T.max() - 365 * 86400
    thr = float(np.quantile(sc[last], Q))
    out = {"ver": 3, "kind": "ema_touch", "feats": F, "models": models, "thr": round(thr, 6), "q": Q, "lab": LAB,
           "rule": {"stop_datr": STOP, "take_r": TAKE, "hold_h": int(HOLD * 24)}, "side_cap": 12, "trained_to": int(T.max()),
           "research": {"coins": 127, "cap": 12, "q": Q, "years": years}}
    json.dump(out, open(f"{D}/vp_ema_model_far.json", "w"), separators=(",", ":"))
    print("thr", thr, "KB", os.path.getsize(f"{D}/vp_ema_model_far.json") // 1024, flush=True)
