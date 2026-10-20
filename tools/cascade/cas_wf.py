"""EMA cascade cross: walk-forward LightGBM on the event context + the 89 Neuro features, top q per side, replay"""
import os, sys, glob
ARGS = sys.argv[1:]
import numpy as np, lightgbm as lgb
from mk import ts
from common import D
import nx_feat
CN = ["s", "rng", "prior", "since_opp", "exc", "move24", "width", "b24", "atrp"]
NAMES = CN + nx_feat.NAMES
if not os.path.exists(f"{D}/cas_all.npz"):
    Xs, Ys, Ts, Ss = [], [], [], []
    for k, fn in enumerate(sorted(glob.glob(f"{D}/cas/*.npz"))):
        z = np.load(fn); sym = os.path.basename(fn)[:-4]
        nf = np.load(f"{D}/nxf/{sym}.npz"); pos = {int(t) + 3600: i for i, t in enumerate(nf["t"])}
        F = z["F"]; idx = np.array([pos.get(int(t), -1) for t in F[:, 0]]); ok = idx >= 0
        Xs.append(np.hstack([F[ok, 1:].astype(np.float32), nf["X"][idx[ok]]])); Ys.append(z["Y"][ok]); Ts.append(F[ok, 0].astype(np.int64))
        Ss.append(np.full(ok.sum(), k, np.int16))
    np.savez(f"{D}/cas_all.npz", X=np.concatenate(Xs), Y=np.concatenate(Ys), T=np.concatenate(Ts), SY=np.concatenate(Ss))
z = np.load(f"{D}/cas_all.npz"); X, Y, T, SY = z["X"], z["Y"], z["T"], z["SY"]
SD = X[:, 0].astype(int)
print("events", len(T), flush=True)
YRS = (2022, 2023, 2024, 2025)
def yr_mask(y): return (T >= ts(y)) & (T < (ts(y + 1) if y < 2025 else ts(2027)))
def wk(y): return ((ts(y + 1) if y < 2025 else ts(2026, 10)) - ts(y)) / (7 * 86400)
def replay(sel, lab, hold, cap=12):
    o = sel[np.argsort(T[sel], kind="stable")]; busy, act, out = {}, [], []
    for j in o:
        t = T[j]; key = (SY[j], SD[j])
        if busy.get(key, 0) > t: continue
        act = [a for a in act if a[0] > t]
        if cap and sum(1 for a in act if a[1] == SD[j]) >= cap: continue
        end = t + hold * 3600; busy[key] = end; act.append((end, SD[j]))
        if lab[j] == lab[j]: out.append((end, float(lab[j]), SD[j]))
    return out
def fmt(out, y):
    if not out: return "—"
    out.sort(); rs = np.array([r for _, r, _ in out]); c = np.r_[0, np.cumsum(rs)]
    dd = float(np.max(np.maximum.accumulate(c) - c)); ns = sum(1 for o in out if o[2] < 0)
    return f"{rs.mean():+.2f}R wr{(rs > 0).mean():.0%} {len(rs) / wk(y):.0f}/нед (ш{ns}) dd{dd:.0f}"
STOPS = ("1", "1.5", "2", "sw"); EXITS = ("t1", "t2", "t3", "cas"); HOLDS = (24, 48)
rules = [a.split("_") for a in ARGS] or [["sw", "t2", "48"], ["2", "t3", "48"], ["1.5", "t2", "24"], ["sw", "cas", "48"]]
SIDES = (1, -1)
for r in rules:
    si, xi, hi = STOPS.index(r[0]), EXITS.index(r[1]), HOLDS.index(int(r[2]))
    lab = Y[:, si, xi, hi]; hold = HOLDS[hi]
    res = {q: [] for q in (0.95, 0.98, 0.99, 0.995)}; base = []
    side_res = {q: [] for q in res}
    for y in YRS:
        tr = T < ts(y) - 10 * 86400; ref = (T >= ts(y - 1)) & (T < ts(y) - 10 * 86400); te = yr_mask(y)
        sc = np.full(len(T), -9.0)
        for s in SIDES:
            ok = np.where(tr & (SD == s) & ~np.isnan(lab))[0]
            if len(ok) > 400000: ok = np.random.default_rng(1).choice(ok, 400000, replace=False)
            m = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1,
                                  colsample_bytree=0.5, reg_lambda=10.0, verbose=-1, n_jobs=4, random_state=1).fit(X[ok, 1:], lab[ok].clip(-1.5, 4))
            w = (SD == s) & (ref | te); sc[w] = m.predict(X[w, 1:])
        base.append(fmt(replay(np.where(te)[0], lab, hold), y))
        for q in res:
            sel = []
            for s in SIDES:
                thr = float(np.quantile(sc[ref & (SD == s)], q)); sel.append(np.where(te & (SD == s) & (sc >= thr))[0])
            res[q].append(fmt(replay(np.concatenate(sel), lab, hold), y))
    print(f"\n== стоп {r[0]} выход {r[1]} {hold}ч", flush=True)
    print("  все события: " + " | ".join(f"{y}: {s}" for y, s in zip(YRS, base)), flush=True)
    for q, v in res.items():
        print(f"  топ {100 - q * 100:.1f}%: " + " | ".join(f"{y}: {s}" for y, s in zip(YRS, v)), flush=True)
