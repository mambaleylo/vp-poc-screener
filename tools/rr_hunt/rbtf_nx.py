"""Neuro filters on the range breakout: (a) the Neuro model's own score for the side (its fold trained before the
year), (b) a model on the 89 Neuro features + the breakout's own, walk-forward; keep the best share of signals"""
import os, sys, glob, pickle, numpy as np, lightgbm as lgb
from mk import ts
import nx_feat
TFH = int(os.environ.get("TFH", 24))
N0, K0, GATE, SK, XN, CAP = int(os.environ.get("N", 20)), float(os.environ.get("K", 2.5)), os.environ.get("GATE", "own200"), float(os.environ.get("SK", 1.5)), os.environ.get("XN", "dc20"), int(os.environ.get("CAP", 6))
import rb_tf as R
# Neuro fold scores (rule 1R stop, 3R take, 48 h): position of (coin, 1h bar) in the saved arrays
S = np.load("nx_sc_1.0_3.0_48.0.npz")
pos, off = {}, 0
for fn in sorted(glob.glob("nx/*.npz")):
    z = np.load(fn)
    if not len(z["t"]):
        continue
    ok = z["X"][:, nx_feat.NAMES.index("atr_pct")] >= 0.1
    ii = z["i"][ok]
    pos[os.path.basename(fn)[:-4]] = (dict(zip(ii.tolist(), range(off, off + len(ii)))))
    off += len(ii)
ev = []
for k, fn in enumerate(sorted(glob.glob(f"rbtf{TFH}/*.pkl"))):
    sym = os.path.basename(fn)[:-4]
    P = pos.get(sym, {})
    for t, s, f, x, y in pickle.load(open(fn, "rb")):
        if f["N"] != N0 or f["rg"] >= K0:
            continue
        g = f["own200"] if GATE == "own200" else (f["d200"] if GATE == "d200" else (f["own200"] and f["d200"]))
        if not g:
            continue
        p = P.get(f["k1"], P.get(f["k1"] - 1))
        ev.append((t, k, s, f, x, y, p))
T = np.array([e[0] for e in ev]); SY = np.array([e[1] for e in ev]); SD = np.array([e[2] for e in ev])
BRK = np.array([e[3]["brk"] for e in ev]); RG = np.array([e[3]["rg"] for e in ev])
X = np.hstack([np.stack([e[4] for e in ev]), np.stack([RG, BRK, SD.astype(float)], 1)])
si, xi = R.STOPS.index(SK), R.EXITS.index(XN)
Yr = np.array([e[5][si, xi, 0] for e in ev], dtype=float); Yj = np.array([e[5][si, xi, 1] for e in ev])
NXP = np.array([-1 if e[6] is None else e[6] for e in ev])
print(f"[{TFH}ч N{N0} <{K0} {GATE} стоп {SK} {XN} лимит {CAP}] сигналов {len(T)}, с оценкой Нейро {(NXP >= 0).mean() * 100:.0f}%", flush=True)
YRS = (2022, 2023, 2024, 2025)
WK = {y: ((ts(y + 1) if y < 2025 else ts(2026, 10)) - ts(y)) / (7 * 86400) for y in YRS}
def replay(idx):
    o = idx[np.lexsort((-BRK[idx], T[idx]))]
    busy, act, out = {}, [], []
    for i in o:
        kk = (SY[i], SD[i]); t = T[i]
        if busy.get(kk, 0) > t or Yr[i] != Yr[i]:
            continue
        act = [a for a in act if a[0] > t]
        if CAP and sum(1 for a in act if a[1] == SD[i]) >= CAP:
            continue
        end = t + int(Yj[i]) * TFH * 3600; busy[kk] = end; act.append((end, SD[i])); out.append((end, Yr[i]))
    return out
def fmt(out, y):
    if not out:
        return "—"
    rs = np.array([o[1] for o in sorted(out)]); c = np.cumsum(rs)
    dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], c])) - np.concatenate([[0], c])))
    return f"{rs.mean():+.2f}R×{len(rs) / WK[y]:.1f} WR{(rs > 0).mean() * 100:.0f} dd{dd:.0f}"
lines = {}
for y in YRS:
    te = (T >= ts(y)) & (T < (ts(y + 1) if y < 2025 else ts(2027)))
    lines.setdefault("все сигналы", []).append(fmt(replay(np.where(te)[0]), y))
    # (a) Neuro's own score for the side, its fold trained before the year
    sc = np.full(len(T), np.nan)
    for s in (1, -1):
        m = te & (SD == s) & (NXP >= 0)
        sc[m] = S[f"{y}_{s}"][NXP[m]]
    for keep in (0.7, 0.5, 0.3):
        thr = np.nanquantile(sc[te], 1 - keep) if np.isfinite(sc[te]).any() else np.inf
        lines.setdefault(f"оценка Нейро: лучшие {int(keep * 100)}%", []).append(fmt(replay(np.where(te & (sc >= thr))[0]), y))
    # (b) a model on the Neuro features + the breakout's own (trained on trades that ENDED before the year)
    end = T + np.nan_to_num(Yj, nan=0) * TFH * 3600
    tr = (end < ts(y)) & ~np.isnan(Yr)
    if tr.sum() <= 200:
        for k in ("модель на признаках Нейро: лучшие 70%", "модель на признаках Нейро: лучшие 50%", "модель на признаках Нейро: лучшие 30%",
                  "модель «шанс плюса»: лучшие 50%", "модель «шанс плюса»: лучшие 30%"):
            lines.setdefault(k, []).append("мало истории")
    else:
        mdl = lgb.LGBMRegressor(n_estimators=200, learning_rate=0.03, num_leaves=7, min_child_samples=50, subsample=0.8, subsample_freq=1,
                                colsample_bytree=0.5, reg_lambda=10.0, verbose=-1, n_jobs=4, random_state=1).fit(X[tr], Yr[tr].clip(-1.5, 10))
        p_tr, p_te = mdl.predict(X[tr]), mdl.predict(X[te])
        for keep in (0.7, 0.5, 0.3):
            thr = np.quantile(p_tr, 1 - keep)
            idx = np.where(te)[0][p_te >= thr]
            lines.setdefault(f"модель на признаках Нейро: лучшие {int(keep * 100)}%", []).append(fmt(replay(idx), y))
        # and a win-probability model (for the win rate)
        clf = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.03, num_leaves=7, min_child_samples=50, subsample=0.8, subsample_freq=1,
                                 colsample_bytree=0.5, reg_lambda=10.0, verbose=-1, n_jobs=4, random_state=1).fit(X[tr], (Yr[tr] > 0).astype(int))
        q_tr, q_te = clf.predict_proba(X[tr])[:, 1], clf.predict_proba(X[te])[:, 1]
        for keep in (0.5, 0.3):
            thr = np.quantile(q_tr, 1 - keep)
            idx = np.where(te)[0][q_te >= thr]
            lines.setdefault(f"модель «шанс плюса»: лучшие {int(keep * 100)}%", []).append(fmt(replay(idx), y))
for k, v in lines.items():
    print(f"{k:38s} " + " | ".join(f"{y}: {s}" for y, s in zip(YRS, v)), flush=True)
