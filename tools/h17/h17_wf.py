"""H17 step 3 — a model on the calm-range events (h17_ev.py), walk-forward like P/R's (prv_wf.py): for each year a LightGBM per
side trained on the events before it (10 days' gap), its threshold the q-quantile of the year before's scores, the year's events
above it traded — one trade a coin & side for its hold, at most 12 a side at once. The rule (stop x take) and q are chosen on
2022–2024; 2025 and 2026 (to the data's end) are shown, never seen by the choice. usage: h17_wf.py"""
import os, sys, glob, calendar, itertools, numpy as np, lightgbm as lgb
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from h17_ev import STOPS, TAKES, HOLD
D = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
ts = lambda y, m=1: calendar.timegm((y, m, 1, 0, 0, 0))
Xs, Ys, Ts, Ss = [], [], [], []
for k, fn in enumerate(sorted(glob.glob(f"{D}/h17_ev/*.npz"))):
    z = np.load(fn)
    if len(z["t"]):
        Xs.append(z["X"]); Ys.append(z["Y"]); Ts.append(z["t"]); Ss.append(np.full(len(z["t"]), k, dtype=np.int16))
X = np.concatenate(Xs); Y = np.concatenate(Ys); T = np.concatenate(Ts); SY = np.concatenate(Ss)
Y = np.where(np.abs(Y) > 20, np.nan, Y); SD = X[:, 0].astype(int)
END = int(T.max())
YRS = (2022, 2023, 2024, 2025, 2026)
yr = lambda y: (T >= ts(y)) & (T < ts(y + 1))
wk = lambda y: (min(ts(y + 1), END) - ts(y)) / (7 * 86400)
print("событий", len(T), "до", __import__("time").strftime("%Y-%m-%d", __import__("time").gmtime(END)), flush=True)


def replay(sel, lab, cap=12):
    o = sel[np.argsort(T[sel], kind="stable")]; busy, act, out = {}, [], []
    for j in o:
        t = T[j]; key = (SY[j], SD[j])
        if busy.get(key, 0) > t:
            continue
        act = [a for a in act if a[0] > t]
        if cap and sum(1 for a in act if a[1] == SD[j]) >= cap:
            continue
        end = t + HOLD * 3600; busy[key] = end; act.append((end, SD[j]))
        if lab[j] == lab[j]:
            out.append((end, float(lab[j])))
    return out


def stat(out, y):
    if not out:
        return (0, 0.0, 0.0, 0.0)
    out.sort(); rs = np.array([r for _, r in out]); c = np.cumsum(rs)
    dd = float(np.max(np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c]))
    return (len(rs), round(float(rs.mean()), 3), round(len(rs) / wk(y), 1), round(dd, 1))


pr = dict(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=500, subsample=0.7, subsample_freq=1,
          colsample_bytree=0.5, reg_lambda=10.0, verbose=-1, n_jobs=4, random_state=1)
QS = (0.9, 0.95, 0.98, 0.99)
res = {}
for si, ti in itertools.product(range(len(STOPS)), range(len(TAKES))):
    lab = Y[:, si, ti]; key = (STOPS[si], TAKES[ti]); res[key] = {q: {} for q in QS}
    base = {y: stat(replay(np.where(yr(y) & ~np.isnan(lab))[0], lab), y) for y in YRS}
    res[key]["all"] = base
    for y in YRS:
        tr = T < ts(y) - 10 * 86400; ref = (T >= ts(y - 1)) & (T < ts(y) - 10 * 86400); te = yr(y)
        sc = np.full(len(T), -9.0)
        for s in (1, -1):
            ok = tr & (SD == s) & ~np.isnan(lab)
            m = lgb.LGBMRegressor(**pr).fit(X[ok], np.clip(lab[ok], -1.5, 3))
            w = (SD == s) & (ref | te); sc[w] = m.predict(X[w])
        for q in QS:
            sel = []
            for s in (1, -1):
                thr = float(np.quantile(sc[ref & (SD == s)], q))
                sel.append(np.where(te & (SD == s) & (sc >= thr))[0])
            res[key][q][y] = stat(replay(np.concatenate(sel), lab), y)
    print(f"стоп {key[0]} тейк {key[1]}: все события " + " | ".join(f"{y} {base[y][1]:+.3f}R" for y in YRS), flush=True)
rows = []
for key, v in res.items():
    for q in QS:
        d = [v[q][y] for y in (2022, 2023, 2024)]; c = [v[q][y] for y in (2025, 2026)]
        n_d = sum(x[0] for x in d); n_c = sum(x[0] for x in c)
        avg = lambda xs: round(sum(x[0] * x[1] for x in xs) / max(1, sum(x[0] for x in xs)), 3)
        rows.append((avg(d), key, q, n_d, avg(c), n_c, [v[q][y] for y in YRS]))
rows.sort(key=lambda r: -r[0])
print("\nправило, топ % | подбор 2022–24: средний R (сделок) | проверка 2025–26: средний R (сделок) | по годам (сделок, R, в неделю, просадка R)")
for r in rows[:10]:
    print(f"стоп {r[1][0]} тейк {r[1][1]}, топ {100 - r[2] * 100:.0f}% | {r[0]:+.3f} ({r[3]}) | {r[4]:+.3f} ({r[5]}) | {r[6]}", flush=True)
best = rows[0]
print(f"\nвыбранное на подборе: стоп {best[1][0]} ATR, тейк {best[1][1]}, топ {100 - best[2] * 100:.0f}% -> проверка 2025–26: {best[4]:+.3f}R на {best[5]} сделках")
print("в плюсе на проверке из первых 10 по подбору:", sum(1 for r in rows[:10] if r[4] > 0))
print("h17 wf done")
