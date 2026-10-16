"""EMA touches: walk-forward LightGBM per trade rule; live-like replay (one per coin & side, cap per side)"""
import os, sys, json
LABS = sys.argv[1:]
import numpy as np, pandas as pd, lightgbm as lgb
from mk import ts, HOLD_S
from common import D
import pyarrow.parquet as pq
names = pq.ParquetFile(f"{D}/er_all.parquet").schema.names
META = {"sym", "t", "j", "tf_s", "n_i", "lv"}
F = [c for c in names if c not in META and c.split("_")[0] not in ("E", "F")]
FINAL = os.environ.get("FINAL") == "1"
YEARS = (2022, 2023, 2024, 2025) if FINAL else (2022, 2023, 2024)
QS = [float(q) for q in os.environ.get("QS", "0.9,0.95,0.98").split(",")]
CAP = int(os.environ.get("CAP", 12))
def replay(sub, sc, thr, lab, cap):
    m = sc >= thr
    s = sub.loc[m, ["t", "sym", "side", lab, lab + "_h"]].copy()
    s["sc"] = sc[m]
    s = s.sort_values(["t", "sc"], ascending=[True, False])
    busy, act, out = {}, [], []
    for t, sym, side, r, h, _ in s.itertuples(index=False):
        if busy.get((sym, side), 0) > t:
            continue
        act = [a for a in act if a[0] > t]
        if cap and sum(1 for a in act if a[1] == side) >= cap:
            continue
        end = t + int(h) * 3600
        busy[(sym, side)] = end
        act.append((end, side))
        out.append((end, r))
    return out

def summ(out, wk):
    if not out:
        return {"n": 0, "avg": 0, "wk": 0, "sum": 0, "dd": 0}
    out.sort()
    rs = np.array([r for _, r in out]); cum = np.cumsum(rs)
    dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], cum])) - np.concatenate([[0], cum])))
    return {"n": len(rs), "avg": round(float(rs.mean()), 3), "wk": round(len(rs) / wk, 1), "sum": round(float(rs.sum()), 1), "dd": round(dd, 1)}

if __name__ == "__main__":
    cols = list(META) + F + [c for l in LABS for c in (l, l + "_h")]
    d = pd.read_parquet(f"{D}/er_all.parquet", columns=cols)
    X = d[F].values.astype(np.float32); T = d.t.values
    
    res = {}
    for lab in LABS:
        y = np.nan_to_num(d[lab].values, nan=0.0).clip(-1.5, 6.0)
        for Y in YEARS:
            tr = T < ts(Y) - 21 * 86400
            sc = np.zeros(len(T))
            for s_ in range(2):
                sc += lgb.LGBMRegressor(n_estimators=500, learning_rate=0.02, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1,
                                        colsample_bytree=0.6, reg_lambda=5.0, verbose=-1, n_jobs=4, random_state=s_).fit(X[tr], y[tr]).predict(X) / 2
            ref = (T >= ts(Y - 1)) & (T < ts(Y) - 21 * 86400)
            te = (T >= ts(Y)) & (T < (ts(Y + 1) if Y < 2025 else ts(2027)))
            sub = d[te].reset_index(drop=True)
            wk = ((ts(Y + 1) if Y < 2025 else ts(2026, 10)) - ts(Y)) / (7 * 86400)
            for q in QS:
                thr = float(np.quantile(sc[ref], q))
                res.setdefault(lab, {}).setdefault(q, {})[Y] = summ(replay(sub, sc[te], thr, lab, CAP), wk)
        for q in QS:
            v = res[lab][q]
            print(f"{lab:14s} top{100 - q * 100:.0f}%: " + " | ".join(f"{Y}: {s['avg']:+.2f}R×{s['wk']}/нед Σ{s['sum']} dd{s['dd']}" for Y, s in v.items()), flush=True)
    json.dump({l: {str(q): v for q, v in x.items()} for l, x in res.items()}, open(f"{D}/er_wf_{'_'.join(LABS)[:60]}.json", "w"))
