"""High-RR hunt: a model per side over the events (all indicators pooled, the indicator is a feature), walk-forward;
top q per side on the last training year; one trade per coin & side until its exit, at most CAP per side"""
import os, sys, glob, json
ARGS = sys.argv[1:]
import numpy as np, lightgbm as lgb
from mk import ts
from common import D
import ev_engine as E
SUB = os.environ.get("SUB", "all")          # all | 4h1d | 1d | fam:<name>
QS = [float(q) for q in os.environ.get("QS", "0.95,0.98,0.99,0.995").split(",")]
CAP = int(os.environ.get("CAP", 12))
Xs, Ys, Ts, FA, TF, SD, SY = [], [], [], [], [], [], []
for k, fn in enumerate(sorted(glob.glob(f"{D}/ev/*.npz"))):
    z = np.load(fn)
    Xs.append(z["X"]); Ys.append(z["Y"]); Ts.append(z["t"]); FA.append(z["fam"]); TF.append(z["tf"]); SD.append(z["side"]); SY.append(np.full(len(z["t"]), k))
X = np.concatenate(Xs); Y = np.concatenate(Ys); T = np.concatenate(Ts); FA = np.concatenate(FA); TF = np.concatenate(TF); SD = np.concatenate(SD); SY = np.concatenate(SY)
del Xs, Ys
m = np.ones(len(T), bool)
if SUB == "4h1d":
    m = TF >= 4
elif SUB == "1d":
    m = TF == 24
elif SUB.startswith("fam:"):
    m = FA == E.FAMS.index(SUB[4:])
X, Y, T, FA, TF, SD, SY = X[m], Y[m], T[m], FA[m], TF[m], SD[m], SY[m]
if os.environ.get("BR") == "1":   # the market's state: breadth across the coins + BTC's daily trend (known after the day closed)
    import pandas as pd
    from common import load as _load
    br = pd.read_pickle(f"{D}/breadth.pkl")
    bt = br.index.values + 86400
    k = np.searchsorted(bt, T, side="right") - 1
    cols = []
    for c in ("above50", "above200", "med7", "med30", "btc_vs_alt30", "disp7"):
        v = np.where(k >= 0, br[c].values[np.maximum(k, 0)], np.nan).astype(np.float32)
        cols += [v, v * SD if c.startswith("med") or c == "btc_vs_alt30" else (v - 0.5) * SD]
    b1 = _load("BTCUSDT"); dcl = {}
    for c_ in b1:
        dcl[c_["time"] // 86400] = c_["close"]
    days = np.array(sorted(dcl)); cl = np.array([dcl[d] for d in days])
    s200 = np.array([cl[max(0, i - 199):i + 1].mean() for i in range(len(cl))])
    r30 = np.array([(cl[i] / cl[i - 30] - 1) * 100 if i >= 30 else 0.0 for i in range(len(cl))])
    kk = np.searchsorted((days + 1) * 86400, T, side="right") - 1
    d200 = np.where(kk >= 0, (cl[np.maximum(kk, 0)] / s200[np.maximum(kk, 0)] - 1) * 100, 0.0)
    cols += [d200.astype(np.float32), (d200 * SD).astype(np.float32), (r30[np.maximum(kk, 0)] * SD).astype(np.float32)]
    X = np.hstack([X, np.stack(cols, axis=1)])
    print("market features added", X.shape, flush=True)
print("events", len(T), SUB, flush=True)
def wk(y):
    return ((ts(y + 1) if y < 2025 else ts(2026, 10)) - ts(y)) / (7 * 86400)
def replay(sel, r, j):
    o = sel[np.argsort(T[sel], kind="stable")]
    busy, act, out = {}, [], []
    for i in o:
        t = T[i]; key = (SY[i], SD[i])
        if busy.get(key, 0) > t or r[i] != r[i]:
            continue
        act = [a for a in act if a[0] > t]
        if CAP and sum(1 for a in act if a[1] == SD[i]) >= CAP:
            continue
        end = t + int(j[i]) * TF[i] * 3600
        busy[key] = end; act.append((end, SD[i]))
        out.append((int(end), float(r[i]), int(FA[i]), int(TF[i])))
    return out
def fmt(out, y):
    if not out:
        return "—", 0, 0
    out.sort(); rs = np.array([o[1] for o in out]); c = np.cumsum(rs)
    dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], c])) - np.concatenate([[0], c])))
    return f"{rs.mean():+.2f}R×{len(rs) / wk(y):.1f}/нед WR{(rs > 0).mean() * 100:.0f} dd{dd:.0f}", rs.sum(), len(rs)
RULES = [r.split("_") for r in ARGS] or [["1.5", "dc20"], ["1.5", "ch5"], ["1.5", "t8"], ["3.0", "dc20"]]
for sk, ex in RULES:
    si, xi = E.STOPS.index(float(sk)), E.EXITS.index(ex)
    r, j = Y[:, si, xi, 0].astype(float), Y[:, si, xi, 1].astype(float)
    r = np.where(np.abs(r) > 60, np.nan, r)
    res = {q: [] for q in QS}; TR = {}
    for y in (2022, 2023, 2024, 2025):
        # training only on events whose trade had ENDED before the test year (no peeking through long holds)
        end = T + np.nan_to_num(j, nan=0) * TF * 3600
        tr = (end < ts(y)) & ~np.isnan(r)
        ref = (T >= ts(y - 1)) & (T < ts(y))
        te = (T >= ts(y)) & (T < (ts(y + 1) if y < 2025 else ts(2027)))
        sc = np.full(len(T), -99.0)
        for s in (1, -1):
            ok = tr & (SD == s)
            mdl = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=500, subsample=0.7, subsample_freq=1,
                                    colsample_bytree=0.5, reg_lambda=10.0, verbose=-1, n_jobs=4, random_state=1).fit(X[ok], r[ok].clip(-1.5, 10.0))
            w = (SD == s) & (ref | te)
            sc[w] = mdl.predict(X[w])
        for q in QS:
            sel = []
            for s in (1, -1):
                thr = q if os.environ.get("THR") == "abs" else float(np.quantile(sc[ref & (SD == s)], q))
                sel.append(np.where(te & (SD == s) & (sc >= thr))[0])
            out = replay(np.concatenate(sel), r, j)
            res[q].append(fmt(out, y)); TR.setdefault(str(q), {})[y] = out
        print(sk, ex, y, "done", flush=True)
    json.dump(TR, open(f"{D}/ev_trades_{SUB.replace(':', '-')}{'_br' if os.environ.get('BR') == '1' else ''}_{sk}_{ex}.json", "w"))
    for q in QS:
        tot = sum(v[1] for v in res[q]); n = sum(v[2] for v in res[q])
        lab_q = f"оценка≥{q}" if os.environ.get("THR") == "abs" else f"топ {100 - q * 100:.1f}%"
        print(f"[{SUB}{'+рынок' if os.environ.get('BR') == '1' else ''}] стоп {sk} выход {ex} {lab_q}: " + " | ".join(f"{y}: {v[0]}" for y, v in zip((2022, 2023, 2024, 2025), res[q])) + f" || всего {tot / max(n, 1):+.2f}R×{n}", flush=True)
