"""strong zones: export the chosen stop / take (LAB) — 3 models on all data, the research block and the monthly
expectation from the capped walk-forward trades of zm_expect2.py"""
import os, json, datetime as dt
from collections import defaultdict
LAB, Q = os.environ.get("LAB", "G_0.75_R4.0"), float(os.environ.get("Q", 0.95))
import lightgbm as lgb
from mk import *
from lgbpure import export
tr = json.load(open(f"{D}/zm_expect_{LAB}_{Q}.json"))
years = {}
for Y in (2022, 2023, 2024, 2025):
    rows = sorted(((t["end"], t["r"], t) for t in tr if t["y"] == Y and t["r"] is not None and t["fill"] is not None), key=lambda x: x[0])
    rs = np.array([r for _, r, _ in rows]); cum = np.cumsum(rs)
    dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], cum])) - np.concatenate([[0], cum])))
    wk = ((ts(Y + 1) if Y < 2025 else ts(2026, 10)) - ts(Y)) / (7 * 86400)
    days = np.mean([(e - (t["t"] + t["fill"] * 3600)) / 86400 for e, _, t in rows])
    years[str(Y)] = {"n": len(rs), "avg": round(float(rs.mean()), 3), "sum": round(float(rs.sum()), 1), "dd": round(dd, 1),
                     "wk": round(len(rs) / wk, 1), "wr": round(float((rs > 0).mean() * 100), 1), "days": round(float(days), 1)}
print(json.dumps(years), flush=True)
M = defaultdict(list)
for t in tr:
    if t["r"] is not None and t["fill"] is not None:
        M[dt.datetime.utcfromtimestamp(t["end"]).strftime("%Y-%m")].append(t["r"])
ms = sorted(M); sums = [sum(M[m]) for m in ms]
ent = sorted(t["t"] + t["fill"] * 3600 for t in tr if t["fill"] is not None and t["t"] >= ts(2025))
zd = len({t["t"] // 86400 for t in tr if t["t"] >= ts(2025)})
expect = {"months": [[m, len(M[m]), round(sum(M[m]), 1)] for m in ms if m >= "2025-01"], "all_months": len(ms),
          "pos_months": sum(1 for s in sums if s > 0), "worst": round(min(sums), 1), "best": round(max(sums), 1),
          "max_gap_d": int(round(float(np.max(np.diff(ent))) / 86400)), "zone_days_share": round(zd / ((ts(2026, 10) - ts(2025)) / 86400), 2)}
json.dump(expect, open(f"{D}/zm_expect_const_{LAB}.json", "w"), separators=(",", ":"), ensure_ascii=False)
print(json.dumps(expect)[:300], flush=True)
d = df([LAB]); F = feats(d); X = d[F].values.astype(np.float32); T = d.t.values
y = np.nan_to_num(d[LAB].values, nan=0.0).clip(-1.2, 6.0)
full = T < T.max() - HOLD_S
models, sc = [], np.zeros(len(T))
for s_ in range(3):
    m = lgb.LGBMRegressor(n_estimators=500, learning_rate=0.02, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1,
                          colsample_bytree=0.6, reg_lambda=5.0, verbose=-1, n_jobs=4, random_state=s_).fit(X[full], y[full])
    models.append(export(m.booster_, F)["trees"])
    sc += m.predict(X) / 3
thr = float(np.quantile(sc[T >= T.max() - 365 * 86400], Q))
bk, tk = LAB.split("_")[1], LAB.split("_")[2]
out = {"ver": 2, "rule": {"buf_datr": float(bk), "tp_r": float(tk[1:])}, "feats": F, "models": models, "thr": round(thr, 6), "q": Q, "lab": LAB,
       "trained_to": int(T.max()), "research": {"cap": 12, "q": Q, "coins": 127, "years": years}, "side_cap": 12}
json.dump(out, open(f"{D}/vp_zones_model2.json", "w"), separators=(",", ":"))
print("thr", thr, "KB", os.path.getsize(f"{D}/vp_zones_model2.json") // 1024, flush=True)
