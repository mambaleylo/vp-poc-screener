"""a model picks the short breakouts (rb_short.py events, rbs_feat.py features), the hold 1 / 2 days: LightGBM on the
trade's R, walk-forward by years (trained on every year before the test year, a 2-day gap) -> each test year 2023-2026
the trades whose predicted R clears a threshold, one trade a coin at a time. The rule and the threshold are to be chosen
on 2023-2024, 2025-2026 is the check. -> <LABSTORE>/wf/rbs_ml.json + the table"""
import sys, os, json, numpy as np, lightgbm as lgb
from multiprocessing import Pool
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
TFS = [int(x) for x in os.environ.get("TFS", "1,2,4").split(",")]
STOPS = (1.0, 1.5, 2.0); EXITS = ("t2", "t3", "dc10", "dc20", "p1t3", "p1dc10"); HOLDS = (1, 2, 5)
RULES = [(sk, xn, hd) for sk in (1.5, 2.0) for xn in ("t2", "t3", "p1t3", "dc10") for hd in (1, 2)]
TEST = (2023, 2024, 2025, 2026); WK = {2023: 52, 2024: 52, 2025: 52, 2026: 43}
THR = tuple(float(x) for x in os.environ.get("THR", "0,0.05,0.1,0.15,0.2,0.3,0.4").split(","))
P = dict(objective="regression", learning_rate=0.05, num_leaves=31, min_data_in_leaf=300, feature_fraction=0.8, bagging_fraction=0.8,
         bagging_freq=1, lambda_l2=10.0, verbose=-1, num_threads=1, seed=1)


def year(t):
    return (1970 + (t / 86400 + 0.5) / 365.2425).astype(int)


def ystart(Y):
    return (np.datetime64(f"{Y}-01-01") - np.datetime64("1970-01-01")).astype("timedelta64[s]").astype(int)


def dedupe(sym, t, bars, tfh):
    keep = np.zeros(len(t), bool); last = {}
    for k in np.lexsort((t, sym)):
        if t[k] >= last.get(sym[k], -1):
            keep[k] = True; last[sym[k]] = t[k] + bars[k] * tfh * 3600
    return keep


_D = {}


def job(a):
    tfh, rule = a
    if tfh not in _D:
        z = dict(np.load(f"{ST}/wf/rbs_{tfh}.npz")); X = np.load(f"{ST}/wf/rbs_{tfh}_X.npz")["X"]
        _D[tfh] = (z["t"], z["sym"], z["y"], X)
    t, sym, y, X = _D[tfh]
    sk, xn, hd = rule
    r = y[:, STOPS.index(sk), EXITS.index(xn), HOLDS.index(hd), 0]; b = y[:, STOPS.index(sk), EXITS.index(xn), HOLDS.index(hd), 1]
    ok = np.isfinite(r); yr = year(t)
    pred = np.full(len(t), np.nan)
    for Y in TEST:
        tr = ok & (t < ystart(Y) - hd * 86400); te = ok & (yr == Y)
        m = lgb.train(P, lgb.Dataset(X[tr], np.clip(r[tr], -1.5, 4.0)), num_boost_round=300)
        pred[te] = m.predict(X[te])
    out = {"tf": tfh, "rule": f"стоп {sk:g} ATR, {xn}, до {hd} сут", "all": {}, "thr": {}}
    for Y in TEST:
        m_ = ok & (yr == Y); out["all"][Y] = [float(r[m_].mean()), float(m_.sum() / WK[Y])]
    for th in THR:
        sel = np.flatnonzero(ok & np.isfinite(pred) & (pred > th))
        kp = sel[dedupe(sym[sel], t[sel], b[sel], tfh)]
        row = {}
        for Y in TEST:
            k_ = kp[yr[kp] == Y]
            row[Y] = [float(r[k_].mean()) if len(k_) else None, float(len(k_) / WK[Y])]
        out["thr"][th] = row
    return out


if __name__ == "__main__":
    res = []
    with Pool(4) as Pl:
        for o in Pl.imap_unordered(job, [(tf, ru) for tf in TFS for ru in RULES]):
            res.append(o)
            print(o["tf"], o["rule"], "все: " + " ".join(f"{o['all'][Y][0]:+.2f}" for Y in TEST), flush=True)
    json.dump(res, open(f"{ST}/wf/rbs_ml{os.environ.get('OUTSUF', '')}.json", "w"), indent=0)
    best = []
    for o in res:
        for th, row in o["thr"].items():
            a = [row[Y][0] for Y in TEST]; n = [row[Y][1] for Y in TEST]
            if any(x is None for x in a) or min(n[:2]) < 1.0:
                continue
            best.append((np.mean([a[0] * n[0], a[1] * n[1]]), o, th, a, n))   # chosen by R a week on 2023-2024
    best.sort(key=lambda v: -v[0])
    print("\nТФ | правило | порог | 2023 2024 (выбор) | 2025 2026 (проверка) | сделок/нед")
    for v in best[:30]:
        _, o, th, a, n = v
        print(f"{o['tf']}ч | {o['rule']} | >{th} | {a[0]:+.2f} {a[1]:+.2f} | {a[2]:+.2f} {a[3]:+.2f} | " + " ".join(f"{x:.1f}" for x in n), flush=True)
    print("ml done")
