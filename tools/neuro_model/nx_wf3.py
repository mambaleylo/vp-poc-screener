"""Neuro v3 walk-forward: a long and a short model per trade rule; top q of each side; one trade per coin & side,
at most CAP per side; busy for the hold window."""
import os, sys, glob, json
RULES = [tuple(float(x) for x in r.split("_")) for r in sys.argv[1:]] or [(1.5, 2.0, 48)]
import numpy as np, lightgbm as lgb
from mk import ts
from common import D
from nx_build import STOPS, TAKES, HOLDS
if os.environ.get("Y3"):
    TAKES, HOLDS = (3.0, 4.0, 6.0), (12, 48, 120)
QS = [float(q) for q in os.environ.get("QS", "0.99,0.995,0.998").split(",")]
CAP = int(os.environ.get("CAP", 12))
YEARS = (2022, 2023, 2024, 2025) if os.environ.get("FINAL") == "1" else (2022, 2023, 2024)
Xs, Ys, Ts, Ss = [], [], [], []
for k, fn in enumerate(sorted(glob.glob(f"{D}/nx/*.npz"))):
    z = np.load(fn)
    if not len(z["t"]):
        continue
    Xs.append(z["X"]); Ys.append(np.load(fn.replace("/nx/", "/nx3/"))["Y"] if os.environ.get("Y3") else z["Y"]); Ts.append(z["t"]); Ss.append(np.full(len(z["t"]), k, dtype=np.int16))
X = np.concatenate(Xs); Y = np.concatenate(Ys); T = np.concatenate(Ts); SY = np.concatenate(Ss)
del Xs, Ys
import nx_feat
_ok = X[:, nx_feat.NAMES.index("atr_pct")] >= 0.1   # a dead market (no hourly range): no trade, no lesson
X, Y, T, SY = X[_ok], Y[_ok], T[_ok], SY[_ok]
Y = np.where(np.abs(Y) > 20, np.nan, Y)
print("rows", len(T), flush=True)

def replay(t, sym, side, r, hold_h):
    o = np.argsort(t, kind="stable")
    busy, act, out = {}, [], []
    for j in o:
        key = (int(sym[j]), int(side[j]))
        if busy.get(key, 0) > t[j]:
            continue
        act = [a for a in act if a[0] > t[j]]
        if CAP and sum(1 for a in act if a[1] == side[j]) >= CAP:
            continue
        end = t[j] + hold_h * 3600
        busy[key] = end
        act.append((end, side[j]))
        if r[j] == r[j]:
            out.append((int(end), float(r[j]), int(sym[j]), int(side[j]), int(t[j])))
    return out

def summ(out, wk):
    if not out:
        return {"n": 0, "avg": 0, "wk": 0, "sum": 0, "dd": 0, "wr": 0}
    out.sort()
    rs = np.array([o[1] for o in out]); cum = np.cumsum(rs)
    dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], cum])) - np.concatenate([[0], cum])))
    return {"n": len(rs), "avg": round(float(rs.mean()), 3), "wk": round(len(rs) / wk, 1), "sum": round(float(rs.sum()), 1),
            "dd": round(dd, 1), "wr": round(float((rs > 0).mean() * 100), 1)}

for rule in RULES:
    a_i, t_i, h_i = STOPS.index(rule[0]), TAKES.index(rule[1]), HOLDS.index(int(rule[2]))
    lab = {s: Y[:, si, a_i, t_i, h_i] for si, s in enumerate((1, -1))}
    res = {q: {} for q in QS}
    TR = {}
    for Yr in YEARS:
        tr = T < ts(Yr) - 3 * 86400
        te = (T >= ts(Yr)) & (T < (ts(Yr + 1) if Yr < 2025 else ts(2027)))
        ref = (T >= ts(Yr - 1)) & (T < ts(Yr) - 3 * 86400)
        sc = {}
        for s in (1, -1):
            y = np.nan_to_num(lab[s], nan=0.0).clip(-1.5, 4.0)
            ok = tr & ~np.isnan(lab[s])
            m = lgb.LGBMRegressor(n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=2000, subsample=0.5, subsample_freq=1,
                                  colsample_bytree=0.5, reg_lambda=10.0, verbose=-1, n_jobs=4, random_state=1).fit(X[ok], y[ok])
            sc[s] = m.predict(X[te | ref])
        idx_all = np.where(te | ref)[0]
        pos = {v: k for k, v in enumerate(idx_all)}
        te_idx = np.where(te)[0]; ref_idx = np.where(ref)[0]
        wk = ((ts(Yr + 1) if Yr < 2025 else ts(2026, 10)) - ts(Yr)) / (7 * 86400)
        for q in QS:
            t_, sy_, sd_, r_ = [], [], [], []
            for s in (1, -1):
                s_te = sc[s][[pos[v] for v in te_idx]]
                s_ref = sc[s][[pos[v] for v in ref_idx]]
                thr = float(np.quantile(s_ref, q))
                sel = te_idx[s_te >= thr]
                t_.append(T[sel]); sy_.append(SY[sel]); sd_.append(np.full(len(sel), s)); r_.append(lab[s][sel])
            out = replay(np.concatenate(t_), np.concatenate(sy_), np.concatenate(sd_), np.concatenate(r_), int(rule[2]))
            res[q][Yr] = summ(out, wk)
            TR.setdefault(str(q), {})[Yr] = out
        print(rule, Yr, "done", flush=True)
    json.dump(TR, open(f"{D}/nx_trades{os.environ.get('Y3', '')}_{rule[0]}_{rule[1]}_{int(rule[2])}.json", "w"))
    for q in QS:
        print(f"{rule} top{(1 - q) * 100:.1f}%: " + " | ".join(f"{Yr}: {s['avg']:+.2f}R×{s['wk']}/нед WR{s['wr']} Σ{s['sum']:.0f} dd{s['dd']:.0f}" for Yr, s in res[q].items()), flush=True)
