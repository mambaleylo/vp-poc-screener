"""robustness of the open-interest / long-short filters that passed mtest.py: the share dropped 20-50%, 3 bootstrap seeds,
and 2023+ alone (after the thresholds' period). ARGV: module feature top|bottom"""
import sys
MOD, FEAT, WH = sys.argv[1], sys.argv[2], sys.argv[3]
import numpy as np
import mfeat, wr_eval
from wr_eval import stats
from mk import ts
k = mfeat.NAMES.index(FEAT)
if MOD == "rbx":
    import rb_h as B
    from rb_x2 import run as rrun
    T_ROW = B.T; FR = mfeat.at(B.SYM, B.T + B.TF * 3600 - 3600); SIDE = B.SD
    SETS = [("бот", lambda m: rrun(B.BOT & m), 0.45), ("проверка", lambda m: rrun(B.CHECK & m), 0.50)]; REF = B.BOT & (B.T < ts(2023))
else:
    import pandas as pd, ema_h as E
    from ema_core import outcomes
    d = E.d; side, tf, e200 = d.side.values, d.tf_s.values, d.s_d_ema200.values
    bema = pd.read_parquet(f"{E.D}/er_all.parquet", columns=["s_b_ema50"]).s_b_ema50.values
    T_ROW = E.T; base = (side > 0) & (e200 < 10) & (tf != "4h") & (bema > 0); FR = mfeat.at(d.sym.values, E.T - 3600); SIDE = side
    def erun(m, q):
        idx = E.cand(q, base & m); R, K, KD = outcomes(idx, deep=0.2); tr = E.replay(idx, R, K)
        return [(int(E.T[i]), int(E.T[i] + K[i] * 3600), float(R[i]), int(side[i]), int(i)) for i in tr]
    SETS = [("бот", lambda m: erun(m, 0.97), 0.45), ("проверка", lambda m: erun(m, 0.90), 0.50)]; REF = base & (E.T < ts(2023))
v = FR[:, k] * (SIDE if FEAT in mfeat.DIR else 1)
ALL = np.ones(len(T_ROW), bool)
for nm, run, tg in SETS:
    print(f"\n=== {MOD} {FEAT} ({'без верхних' if WH == 'top' else 'без нижних'}), {nm}", flush=True)
    variants = [("сейчас", ALL)]
    for p in (0.2, 0.25, 1 / 3, 0.4, 0.5):
        th = np.nanquantile(v[REF], 1 - p if WH == "top" else p)
        variants.append((f"отсечь {round(p * 100)}%", ~(v > th) if WH == "top" else ~(v < th)))
    for lab, m in variants:
        tr = run(m)
        for seed in (11, 12):
            wr_eval_rng = np.random.default_rng(seed)
            import nx_h; nx_h.rng = wr_eval_rng   # pain() of nx_h is the bootstrap behind wr_eval.stats
            stats(f"{lab} (seed {seed})", tr, ts(2022), tg)
        stats(f"{lab} — только 2023+", tr, ts(2023), tg)
