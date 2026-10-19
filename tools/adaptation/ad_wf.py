"""Adaptation study: for every model indicator (Neuro, P/R, EMA, strong zones) the same out-of-sample months
2023-01 .. 2026-09 under different training schemes — the window (6 / 12 / 24 / 36 months / all history), the
retrain step (1 / 3 / 12 months) and recency weights (half-life). Each retrain: train on [t0 - W - gap, t0 - gap),
the score threshold = the deployed quantile of the new model's scores over the 12 months before t0 - gap, trade
[t0, t0 + step) with the module's own replay (one trade per coin & side, at most 12 per side). The trades are saved
for the regime gates (ad_gate.py)."""
import os, sys, json, time
ARGS = sys.argv[1:]
import numpy as np, lightgbm as lgb, datetime as dt
from common import D
from mk import ts

MOD = ARGS[0]
SCHEMES = {   # name: (window months or None = all, step months, half-life months or None)
    "all_12": (None, 12, None), "all_3": (None, 3, None), "all_1": (None, 1, None),
    "36_3": (36, 3, None), "24_3": (24, 3, None), "12_3": (12, 3, None), "12_1": (12, 1, None), "6_1": (6, 1, None),
    "all_3_hl12": (None, 3, 12), "all_1_hl6": (None, 1, 6),
    "all_12_hl12": (None, 12, 12), "all_3_hl6": (None, 3, 6), "all_3_hl24": (None, 3, 24), "24_12": (24, 12, None), "36_12": (36, 12, None),
}
ONLY = ARGS[1:] or list(SCHEMES)
MAXROWS = int(os.environ.get("MAXROWS", 700000))
rng = np.random.default_rng(int(os.environ.get("SEED", 7)))
SEED = int(os.environ.get("SEED", 1))


def month_add(t, k):
    d = dt.datetime.fromtimestamp(int(t), dt.timezone.utc)
    m = d.month - 1 + k
    return int(dt.datetime(d.year + m // 12, m % 12 + 1, 1, tzinfo=dt.timezone.utc).timestamp())


def load():
    """-> dict: X, T, SY (coin), SD (side), lab (R, NaN = no outcome), HOLD (hours per row), test mask, gap s, q,
    params, per_side (separate models per side)"""
    if MOD == "nx":
        import glob
        Xs, Ys, Ts, Ss = [], [], [], []
        for k, fn in enumerate(sorted(glob.glob(f"{D}/nx/*.npz"))):
            z = np.load(fn)
            if not len(z["t"]):
                continue
            Xs.append(z["X"]); Ys.append(np.load(fn.replace("/nx/", "/nx3/"))["Y"]); Ts.append(z["t"]); Ss.append(np.full(len(z["t"]), k, np.int16))
        X = np.concatenate(Xs); Y = np.concatenate(Ys); T = np.concatenate(Ts); SY = np.concatenate(Ss)
        import nx_feat
        ok = X[:, nx_feat.NAMES.index("atr_pct")] >= 0.1
        X, Y, T, SY = X[ok], Y[ok], T[ok], SY[ok]
        Y = np.where(np.abs(Y) > 20, np.nan, Y)
        # Y3 grid: stops (1.0, 1.5, 2.5), takes (3, 4, 6), holds (12, 48, 120) -> stop 1, take 3R, 48h
        n = len(T)
        X2 = np.concatenate([X, X]); T2 = np.concatenate([T, T]); SY2 = np.concatenate([SY, SY])
        SD2 = np.concatenate([np.ones(n, np.int8), -np.ones(n, np.int8)])
        lab = np.concatenate([Y[:, 0, 0, 0, 1], Y[:, 1, 0, 0, 1]]).astype(np.float64)
        return dict(X=X2, T=T2, SY=SY2, SD=SD2, lab=lab, HOLD=np.full(2 * n, 48.0), test=np.ones(2 * n, bool), gap=3 * 86400, q=0.995,
                    per_side=True, clip=(-1.5, 4.0),
                    params=dict(n_estimators=300, learning_rate=0.04, num_leaves=31, min_child_samples=2000, subsample=0.5, subsample_freq=1,
                                colsample_bytree=0.5, reg_lambda=10.0))
    if MOD == "prv":
        import glob, nx_feat
        from prv_ev import STOPS, TAKES, BAND_NAMES
        Xs, Ys, Ts, Ss = [], [], [], []
        for k, fn in enumerate(sorted(glob.glob(f"{D}/prv_ev/*.npz"))):
            z = np.load(fn)
            if len(z["t"]):
                Xs.append(z["X"]); Ys.append(z["Y"]); Ts.append(z["t"]); Ss.append(np.full(len(z["t"]), k, np.int16))
        X = np.concatenate(Xs); Y = np.concatenate(Ys); T = np.concatenate(Ts); SY = np.concatenate(Ss)
        Y = np.where(np.abs(Y) > 20, np.nan, Y)
        names = BAND_NAMES + nx_feat.NAMES
        SD = X[:, names.index("side")].astype(np.int8); TF = X[:, names.index("tf")]
        lab = Y[:, STOPS.index(1.5), TAKES.index(3.0)].astype(np.float64)
        return dict(X=X, T=T, SY=SY, SD=SD, lab=lab, HOLD=48.0 * TF, test=np.ones(len(T), bool), gap=10 * 86400, q=0.99,
                    per_side=True, clip=(-1.5, 4.0),
                    params=dict(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1,
                                colsample_bytree=0.5, reg_lambda=10.0))
    if MOD == "emx":
        import pandas as pd, pyarrow.parquet as pq
        LAB = "F_0.75_4.0_3"
        names = pq.ParquetFile(f"{D}/er_all.parquet").schema.names
        META = ["sym", "t", "j", "tf_s", "n_i", "lv", "side"]
        F = [c for c in names if c not in META[:-1] and c.split("_")[0] not in ("E", "F")]
        d = pd.read_parquet(f"{D}/er_all.parquet", columns=list(dict.fromkeys(META + F + [LAB, LAB + "_h"])))
        pen = pd.read_parquet(f"{D}/er_pen.parquet").pen.values
        syms = {s: i for i, s in enumerate(sorted(d.sym.unique()))}
        return dict(X=d[F].values.astype(np.float32), T=d.t.values.astype(np.int64), SY=d.sym.map(syms).values.astype(np.int16),
                    SD=d.side.values.astype(np.int8), lab=d[LAB].values.astype(np.float64), HOLD=d[LAB + "_h"].values.astype(np.float64),
                    test=pen >= 0.1, gap=21 * 86400, q=0.97, per_side=False, clip=(-1.5, 5.0),
                    params=dict(n_estimators=500, learning_rate=0.02, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1,
                                colsample_bytree=0.6, reg_lambda=5.0))
    if MOD == "zm":
        import pandas as pd
        from mk import df, feats, HOLD_S
        LAB = "G_0.75_R4.0"
        d = df([LAB, LAB + "_h"]); F = feats(d)
        tm = pd.read_parquet(f"{D}/times.parquet")
        f1, ex = tm.f1.values, tm.ex.values
        hold = np.where((f1 == f1) & (ex == ex), f1 + ex + 1, HOLD_S / 3600.0)
        syms = {s: i for i, s in enumerate(sorted(d.sym.unique()))}
        return dict(X=d[F].values.astype(np.float32), T=d.t.values.astype(np.int64), SY=d.sym.map(syms).values.astype(np.int16),
                    SD=np.where(d.side_s.astype(str).values == "long", 1, -1).astype(np.int8), lab=d[LAB].values.astype(np.float64), HOLD=hold.astype(np.float64),
                    test=np.ones(len(d), bool), gap=HOLD_S, q=0.95, per_side=False, clip=(-1.2, 6.0),
                    params=dict(n_estimators=500, learning_rate=0.02, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1,
                                colsample_bytree=0.6, reg_lambda=5.0))
    raise SystemExit("module?")


def replay(idx, sc, M, cap=12):
    """one trade per coin & side for its hold, at most cap per side; the higher score first at one time"""
    T, SY, SD, HOLD, lab = M["T"], M["SY"], M["SD"], M["HOLD"], M["lab"]
    o = idx[np.lexsort((-sc, T[idx]))]
    busy, act, out = {}, [], []
    for j in o:
        t = int(T[j]); key = (int(SY[j]), int(SD[j]))
        if busy.get(key, 0) > t:
            continue
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == SD[j]) >= cap:
            continue
        end = t + int(HOLD[j] * 3600)
        busy[key] = end; act.append((end, SD[j]))
        if lab[j] == lab[j]:
            out.append((t, end, float(lab[j]), int(SY[j]), int(SD[j])))
    return out


def run_scheme(M, name):
    W, step, hl = SCHEMES[name]
    T, X, lab = M["T"], M["X"], M["lab"]
    y_all = np.nan_to_num(lab, nan=0.0).clip(*M["clip"])
    start, end = ts(2023), ts(2026, 10)
    sel_idx, sel_sc = [], []
    t0 = start
    nfit = 0
    while t0 < end:
        t1 = min(month_add(t0, step), end)
        lo = month_add(t0, -W) - M["gap"] if W else 0
        trm = (T < t0 - M["gap"]) & (T >= lo) & ~np.isnan(lab)
        ref = (T >= month_add(t0, -12) - M["gap"]) & (T < t0 - M["gap"])
        te = (T >= t0) & (T < t1)
        for s in ((1, -1) if M["per_side"] else (None,)):
            side_m = (M["SD"] == s) if s is not None else np.ones(len(T), bool)
            tri = np.where(trm & side_m)[0]
            if len(tri) > MAXROWS:
                tri = np.sort(rng.choice(tri, MAXROWS, replace=False))
            w = None
            if hl:
                age_m = (t0 - T[tri]) / (30.44 * 86400)
                w = 0.5 ** (age_m / hl)
            m = lgb.LGBMRegressor(**M["params"], verbose=-1, n_jobs=4, random_state=SEED).fit(X[tri], y_all[tri], sample_weight=w)
            nfit += 1
            ri = np.where(ref & side_m)[0]
            ti = np.where(te & side_m & M["test"])[0]
            if not len(ti) or not len(ri):
                continue
            thr = float(np.quantile(m.predict(X[ri]), M["q"]))
            sc = m.predict(X[ti])
            k = sc >= thr
            sel_idx.append(ti[k]); sel_sc.append(sc[k])
        t0 = t1
    idx = np.concatenate(sel_idx) if sel_idx else np.array([], int)
    sc = np.concatenate(sel_sc) if sel_sc else np.array([])
    return replay(idx, sc, M), nfit


def summary(out):
    if not out:
        return {"n": 0}
    out = sorted(out, key=lambda o: o[1])
    r = np.array([o[2] for o in out]); te = np.array([o[1] for o in out])
    yrs = {}
    for Y in (2023, 2024, 2025, 2026):
        m = (te >= ts(Y)) & (te < ts(Y + 1))
        if m.any():
            yrs[Y] = round(float(r[m].mean()), 3)
    mon = {}
    for o in out:
        k = dt.datetime.fromtimestamp(o[1], dt.timezone.utc).strftime("%Y-%m"); mon[k] = mon.get(k, 0) + o[2]
    cum = np.cumsum(r); dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], cum])) - np.concatenate([[0], cum])))
    wk = (ts(2026, 10) - ts(2023)) / (7 * 86400)
    return {"n": len(r), "avg": round(float(r.mean()), 3), "sum": round(float(r.sum()), 1), "wk": round(len(r) / wk, 1), "dd": round(dd, 1),
            "mpos": round(100 * np.mean([v > 0 for v in mon.values()]), 0), "years": yrs}


if __name__ == "__main__":
    t_ = time.time()
    M = load()
    print(MOD, "rows", len(M["T"]), "loaded", round(time.time() - t_), flush=True)
    os.makedirs(f"{D}/ad", exist_ok=True)
    for name in ONLY:
        fn = f"{D}/ad/{MOD}_{name}{'_s' + os.environ['SEED'] if os.environ.get('SEED') else ''}.json"
        if os.path.exists(fn):
            s = json.load(open(fn))["summary"]
        else:
            t_ = time.time()
            out, nfit = run_scheme(M, name)
            s = summary(out)
            json.dump({"summary": s, "trades": out}, open(fn, "w"))
            s["sec"] = round(time.time() - t_)
        print(f"{MOD} {name:11s} " + (f"n {s['n']:5d} ({s['wk']}/нед) avg {s['avg']:+.3f}R Σ{s['sum']:+.0f} dd{s['dd']:.0f} мес+ {s['mpos']:.0f}% | "
              + " ".join(f"{y}: {v:+.3f}" for y, v in s["years"].items()) if s["n"] else "no trades") + (f"  [{s.get('sec', '')}s]" if s.get("sec") else ""), flush=True)
