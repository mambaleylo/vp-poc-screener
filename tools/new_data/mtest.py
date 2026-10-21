"""New data (open interest, long/short, taker flow; mfeat.py) as entry filters on every module's deployed rule:
for each feature (× side for the directional ones) drop the top or the bottom third of the module's candidates
(thresholds from the bot's set before 2023), on the bot's and the check set; avg R, WR, equal-pain growth, years.
ARGV: module (prv | emx | rbx | cas | nx)"""
import sys
MOD = sys.argv[1]
import numpy as np
import mfeat
from wr_eval import stats
from mk import ts
def yrs(tr):
    r = np.array([x[2] for x in tr]); t = np.array([x[0] for x in tr])
    return " ".join(f"{r[(t >= ts(y)) & (t < ts(y + 1))].mean():+.2f}" for y in range(2022, 2027))
def report(sets, featrows, side, ref):
    """sets: [(name, mask over rows, target, run)]; run(keep) -> trades, keep = a row mask, or for side=None (Neuro, both
    sides per row) a function side -> mask; featrows: (n, k) features per row; ref: the rows for the thresholds"""
    for nm_, M, tg, run in sets:
        print(f"\n=== {MOD} {nm_}", flush=True)
        allk = (lambda s_: M) if side is None else M
        tr = run(allk); print("   годы", yrs(tr)); stats("сейчас", tr, F0, tg)
        for k, f in enumerate(mfeat.NAMES):
            sg = (lambda s_: s_ if f in mfeat.DIR else 1)
            if side is None:
                vv = {s_: featrows[:, k] * sg(s_) for s_ in (1, -1)}
                los = {s_: np.nanquantile(vv[s_][ref], [1 / 3, 2 / 3]) for s_ in (1, -1)}
                keeps = ((f"{f}: без верхней трети", lambda s_: M & ~(vv[s_] > los[s_][1])), (f"{f}: без нижней трети", lambda s_: M & ~(vv[s_] < los[s_][0])))
            else:
                v = featrows[:, k] * (side if f in mfeat.DIR else 1)
                lo, hi = np.nanquantile(v[ref], [1 / 3, 2 / 3])
                keeps = ((f"{f}: без верхней трети", M & ~(v > hi)), (f"{f}: без нижней трети", M & ~(v < lo)))
            for lab, keep in keeps:
                tr = run(keep); print("   годы", yrs(tr)); stats(lab, tr, F0, tg)
if MOD == "rbx":
    import rb_h as B
    from rb_x2 import run as rrun
    T_ROW = B.T; F0 = ts(2022)
    FR = mfeat.at(B.SYM, B.T + B.TF * 3600 - 3600)
    report([("бот", B.BOT, 0.45, rrun), ("проверка", B.CHECK, 0.50, rrun)], FR, B.SD, B.BOT & (B.T < ts(2023)))
elif MOD == "emx":
    import pandas as pd, ema_h as E
    from ema_core import outcomes
    d = E.d; side, tf, e200 = d.side.values, d.tf_s.values, d.s_d_ema200.values
    bema = pd.read_parquet(f"{E.D}/er_all.parquet", columns=["s_b_ema50"]).s_b_ema50.values
    T_ROW = E.T; F0 = ts(2022)
    base = (side > 0) & (e200 < 10) & (tf != "4h") & (bema > 0)
    FR = mfeat.at(d.sym.values, E.T - 3600)
    def erun(m, q):
        idx = E.cand(q, m); R, K, KD = outcomes(idx, deep=0.2); tr = E.replay(idx, R, K)
        return [(int(E.T[i]), int(E.T[i] + K[i] * 3600), float(R[i]), int(side[i]), int(i)) for i in tr]
    report([("бот q0.97", base, 0.45, lambda m: erun(m, 0.97)), ("проверка q0.90", base, 0.50, lambda m: erun(m, 0.90))], FR, side, base & (E.T < ts(2023)))
elif MOD == "cas":
    import cas_core as CX
    from cas_h import S, SD, T, SY, SYMS
    T_ROW = T; F0 = ts(2022)
    FR = mfeat.at(np.array(SYMS)[SY], T - 3600)
    def crun(m, q):
        orig = CX.SD; CX.SD = np.where(m, SD, 0)
        try: return CX.trades(q)
        finally: CX.SD = orig
    ALL = np.ones(len(T), bool)
    for q, nm, tg in ((0.995, "бот q0.995", 0.45), (0.98, "проверка q0.98", 0.50)):
        print(f"\n### {nm}")
        report([(nm, ALL, tg, lambda m, q=q: crun(m, q))], FR, SD, T < ts(2023))
elif MOD == "nx":
    import nx_h as N
    from nx_x2 import build
    T_ROW = N.T; F0 = ts(2022)
    FR = mfeat.at(np.array(N.SYMS)[N.SY], N.T)
    ALL = np.ones(len(N.T), bool)
    for q, nm, tg in ((0.995, "бот q0.995", 0.45), (0.98, "проверка q0.98", 0.50)):
        print(f"\n### {nm}")
        report([(nm, ALL, tg, lambda kf, q=q: sorted(build(q, filt=kf)))], FR, None, N.T < ts(2023))
elif MOD == "prv":
    import pr_x_eval as X
    P = X.P
    T_ROW = P.T; F0 = ts(2023)
    SYMS = [__import__("os").path.basename(f)[:-4] for f in sorted(__import__("glob").glob("prv_ev/*.npz"))]
    FR = mfeat.at(np.array(SYMS)[P.SY], P.T - 3600)
    z = np.load("p2_base.npz"); r = z["cs"].astype(float)
    P.R = np.where(np.abs(r) > 20, np.nan, r); P.END = P.T + (z["k"].astype(int) + 1) * P.TF * 3600
    def prun(m, q):
        c = X.cands(q); c = c[m[c]]; tr = P.replay(c, cap=12)
        return [(int(P.T[i]), int(P.END[i]), float(P.R[i]), int(P.SD[i]), int(i)) for i in tr]
    ALL = np.ones(len(P.T), bool)
    for q, nm, tg in (("99", "бот q99", 0.45), ("95", "проверка q95", 0.50)):
        print(f"\n### {nm}")
        report([(nm, ALL, tg, lambda m, q=q: prun(m, q))], FR, P.SD, P.T < ts(2023))
