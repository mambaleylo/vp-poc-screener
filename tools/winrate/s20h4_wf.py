"""walk-forward per new family (s16): yearly LightGBM on the train coins (800k at most), the threshold = q of the previous
year's out-of-sample scores; WR / R / a month per set and per year; the scores saved for the later steps"""
import sys
ARGS = sys.argv[1:]
import numpy as np, lightgbm as lgb, warnings; warnings.filterwarnings("ignore")
import s20h4_engine as E
from s15_wf import load, select, report, fmt
from mk import ts
fams = ARGS[0].split(",") if ARGS else E.FAMS
exits = [int(x) for x in ARGS[1].split(",")] if len(ARGS) > 1 else [0, 1]
pr = dict(n_estimators=300, learning_rate=0.05, num_leaves=63, min_child_samples=1000, subsample=0.7, subsample_freq=1, colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=2)
for fam in fams:
    D = load("s20h4", [E.FAMS.index(fam)])
    T, F, TR = D["t"], D["F"], ~D["chk"]
    for e in exits:
        y = np.clip(D["R"][e], -1.5, 1.5); rng = np.random.default_rng(0)
        SC = np.full(len(T), np.nan); THR = {}
        for Y in (2022, 2023, 2024, 2025, 2026):
            tr = np.flatnonzero(TR & (T < ts(Y) - 3 * 86400))
            if len(tr) < 20000: continue
            if len(tr) > 800000: tr = rng.choice(tr, 800000, replace=False)
            m = lgb.LGBMRegressor(random_state=0, **pr).fit(F[tr], y[tr])
            te = (T >= ts(Y)) & (T < ts(Y + 1)); ref = TR & (T >= ts(Y - 1)) & (T < ts(Y))
            need = te | ref; sc = np.full(len(T), np.nan); sc[need] = m.predict(F[need]); SC[te] = sc[te]
            prev = ref & np.isfinite(SC); THR[Y] = SC[prev] if prev.sum() >= 1000 else sc[ref]
        np.savez(f"s20h4_sc_{fam}_{e}.npz", SC=SC, THR=np.array(THR, dtype=object))
        for q in (0.98, 0.99, 0.995):
            a = report(D, e, select(D, e, SC, THR, q, 12, TR)); b = report(D, e, select(D, e, SC, THR, q, 12, D["chk"]))
            print(f"{fam:9s} E{e} {E.EXITS[e]} q{q}  обуч: {fmt(a)}\n{'':30s}  пров: {fmt(b)}", flush=True)
