"""Walk-forward judge for the win-rate hunt (s15 / s5 / s1 event files): per family (or a list of families), per exit.
Coins: every 3rd coin (sorted) is a CHECK coin never trained on, the rest TRAIN. A yearly LightGBM on the train coins'
events closed 3 days before the year (a random 1.5M at most), label = R (clipped); the threshold of a year = the
q-quantile of the previous year's out-of-sample scores of the train coins. Trades: score >= thr, one per coin & side at a
time, at most CAP per side. Prints WR, R, trades a month, the share of weeks with a trade, sum R and the worst drawdown
in R, per set, and the yearly averages.
usage: s15_wf.py DIR ENGINE "fam-list" "exit-list" [q-list] [cap]"""
import sys, os, glob, importlib
ARGS = sys.argv[1:]
import numpy as np, lightgbm as lgb, warnings
warnings.filterwarnings("ignore")
from mk import ts

def load(dr, fams):
    parts = []
    files = sorted(glob.glob(f"{dr}/*.npz"))
    syms = [os.path.basename(f)[:-4] for f in files]
    chk = set(syms[2::3])
    for k, fn in enumerate(files):
        z = np.load(fn)
        m = np.isin(z["fam"], fams)
        if not m.any(): continue
        parts.append(dict(t=z["t"][m].astype(np.int64), side=z["side"][m].astype(np.int8), R=z["R"][:, m], K=z["K"][:, m].astype(np.int32),
                          W=z["W"][:, m], F=z["F"][m], sym=np.full(int(m.sum()), k, np.int32), chk=np.full(int(m.sum()), syms[k] in chk)))
    D = {k: np.concatenate([p[k] for p in parts], axis=(1 if k in ("R", "K", "W") else 0)) for k in parts[0]}
    D["names"] = syms
    return D

def scores(D, e, years=(2022, 2023, 2024, 2025, 2026), seed=0):
    T, F, TR = D["t"], D["F"], ~D["chk"]
    y = np.clip(D["R"][e], -1.5, 1.5)
    rng = np.random.default_rng(seed)
    SC = np.full(len(T), np.nan); THR = {}
    pr = dict(n_estimators=300, learning_rate=0.05, num_leaves=63, min_child_samples=1000, subsample=0.7, subsample_freq=1,
              colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
    for Y in years:
        tr = np.flatnonzero(TR & (T < ts(Y) - 3 * 86400))
        if len(tr) < 20000: continue
        if len(tr) > 1500000: tr = rng.choice(tr, 1500000, replace=False)
        mdl = lgb.LGBMRegressor(random_state=seed, **pr).fit(F[tr], y[tr])
        te = (T >= ts(Y)) & (T < ts(Y + 1))
        ref = TR & (T >= ts(Y - 1)) & (T < ts(Y))
        need = te | ref
        sc = np.full(len(T), np.nan); sc[need] = mdl.predict(F[need])
        SC[te] = sc[te]
        prev = ref & np.isfinite(SC)
        THR[Y] = SC[prev] if prev.sum() >= 1000 else sc[ref]
    return SC, THR

def select(D, e, SC, THR, q, cap, sub):
    T, S, SYM, K = D["t"], D["side"], D["sym"], D["K"][e]
    yr = T.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970
    thr = np.full(len(T), np.inf)
    for Y, v in THR.items():
        thr[yr == Y] = np.quantile(v, q)
    idx = np.flatnonzero(sub & np.isfinite(SC) & (SC >= thr))
    o = idx[np.lexsort((-SC[idx], T[idx]))]
    busy = {}; act = []; out = []
    for i in o:
        t = T[i]; key = (SYM[i], S[i])
        if busy.get(key, 0) > t: continue
        if act:
            act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == S[i]) >= cap: continue
        end = t + int(K[i]) * 3600; busy[key] = end; act.append((end, S[i])); out.append(i)
    return np.array(out, dtype=np.int64)

def report(D, e, sel, t0=None):
    t0 = t0 or ts(2022)
    sel = sel[D["t"][sel] >= t0]
    if len(sel) < 30: return None
    T = D["t"][sel]; R = D["R"][e][sel]; W = D["W"][e][sel]
    mo = (ts(2026, 10) - t0) / (30.4 * 86400); nw = (ts(2026, 10) - t0) / (7 * 86400)
    o = np.argsort(T + D["K"][e][sel] * 3600); c = np.cumsum(R[o]); dd = float(np.max(np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c]))
    yrs = [float(R[(T >= ts(Y)) & (T < ts(Y + 1))].mean()) if ((T >= ts(Y)) & (T < ts(Y + 1))).any() else np.nan for Y in range(2022, 2027)]
    run = mx = 0
    for r in R[o]:
        run = run + 1 if r < 0 else 0; mx = max(mx, run)
    return dict(n=len(sel), pm=len(sel) / mo, wk=len(set((T // 604800).tolist())) / nw, wr=float(W.mean()), R=float(R.mean()), sum=float(R.sum()), dd=dd, streak=mx, yrs=yrs)

def fmt(s):
    if not s: return "—"
    return (f"{s['pm']:6.1f}/мес нед {s['wk']*100:3.0f}% WR {s['wr']*100:3.0f}% {s['R']:+.3f}R Σ{s['sum']:+7.0f}R dd {s['dd']:5.1f}R серия {s['streak']:2d} ["
            + " ".join("  —  " if v != v else f"{v:+.2f}" for v in s["yrs"]) + "]")

if __name__ == "__main__":
    dr, eng = ARGS[0], importlib.import_module(ARGS[1])
    fams = [eng.FAMS.index(f) for f in ARGS[2].split(",")] if ARGS[2] != "all" else list(range(len(eng.FAMS)))
    exits = [int(x) for x in ARGS[3].split(",")]
    QS = [float(x) for x in ARGS[4].split(",")] if len(ARGS) > 4 else [0.9, 0.95, 0.98, 0.99]
    cap = int(ARGS[5]) if len(ARGS) > 5 else 12
    D = load(dr, fams)
    print(f"{ARGS[2]}: {len(D['t'])} events", flush=True)
    for e in exits:
        SC, THR = scores(D, e)
        for q in QS:
            a = report(D, e, select(D, e, SC, THR, q, cap, ~D["chk"]))
            b = report(D, e, select(D, e, SC, THR, q, cap, D["chk"]))
            print(f"{ARGS[2]:16s} E{e} {eng.EXITS[e]} q{q}  обуч: {fmt(a)}\n{'':38s}  пров: {fmt(b)}", flush=True)
