"""zones: every stop x take label in the same honest walk-forward as the deployed rule (q, cap 12 per side,
one zone per coin & side, busy until its exit)"""
import sys, json
A = sys.argv[1:]
import lightgbm as lgb
from mk import *
LABS = A or [f"G_{b}_R{t}" for b in ("0.75", "1.0", "1.5", "2.0") for t in ("1.5", "2.0", "3.0", "4.0", "6.0")]
d = df(LABS + [l + "_h" for l in LABS]); F = feats(d); X = d[F].values.astype(np.float32); T = d.t.values
tm = pd.read_parquet(f"{D}/times.parquet"); F1 = tm.f1.values
SYM = d.sym.values; SIDE = d.side_s.values
def rep(idx, sc, r, h):
    o = idx[np.lexsort((-sc[idx], T[idx]))]
    busy, act, out = {}, [], []
    for j in o:
        t = T[j]; k = (SYM[j], SIDE[j])
        if busy.get(k, 0) > t:
            continue
        end = t + (F1[j] + h[j] + 1) * 3600 if (F1[j] == F1[j] and h[j] == h[j]) else t + HOLD_S
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == SIDE[j]) >= 12:
            continue
        busy[k] = end; act.append((end, SIDE[j]))
        if r[j] == r[j]:
            out.append((end, float(r[j])))
    return out
def summ(out, wk):
    if not out:
        return "n=0"
    out.sort(); rs = np.array([x[1] for x in out]); cum = np.cumsum(rs)
    dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], cum])) - np.concatenate([[0], cum])))
    return f"{rs.mean():+.2f}R×{len(rs) / wk:.1f}/нед WR{(rs > 0).mean() * 100:.0f} Σ{rs.sum():.0f} dd{dd:.0f}", rs.sum(), dd, len(rs)
res = {}
for lab in LABS:
    r = d[lab].values; h = d[lab + "_h"].values
    y = np.nan_to_num(r, nan=0.0).clip(-1.2, 8.0)
    lines = {q: [] for q in (0.95, 0.98)}
    tot = {q: [0, 0, 0] for q in (0.95, 0.98)}
    for Y in (2022, 2023, 2024, 2025):
        tr = T < ts(Y) - HOLD_S
        m = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.035, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1,
                              colsample_bytree=0.6, reg_lambda=5.0, verbose=-1, n_jobs=4, random_state=0).fit(X[tr], y[tr])
        ref = (T >= ts(Y - 1)) & (T < ts(Y) - HOLD_S)
        te = (T >= ts(Y)) & (T < (ts(Y + 1) if Y < 2025 else ts(2027)))
        sc = np.full(len(T), -9.0); w = ref | te; sc[w] = m.predict(X[w])
        wk = ((ts(Y + 1) if Y < 2025 else ts(2026, 10)) - ts(Y)) / (7 * 86400)
        for q in (0.95, 0.98):
            thr = float(np.quantile(sc[ref], q))
            s = summ(rep(np.where(te & (sc >= thr))[0], sc, r, h), wk)
            lines[q].append(f"{Y}: {s[0] if isinstance(s, tuple) else s}")
            if isinstance(s, tuple):
                tot[q][0] += s[1]; tot[q][1] = max(tot[q][1], s[2]); tot[q][2] += s[3]
    for q in (0.95, 0.98):
        print(f"{lab} q{q}: " + " | ".join(lines[q]) + f" || Σ{tot[q][0]:.0f}R за {tot[q][2]} сделок, худшая просадка {tot[q][1]:.0f}R", flush=True)
