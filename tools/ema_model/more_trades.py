"""more trades for the other modules (the user: "а если по другим индикаторам попробовать увеличить количество"):
lower score thresholds and bigger caps on the deployed rules; growth at an equal 1-in-10 drawdown. ARGV: emx | cas | nx | rbx"""
import sys
MOD = sys.argv[1]
import numpy as np
from wr_eval import stats
from mk import ts
def yrs(tr, y0=2022):
    r = np.array([x[2] for x in tr]); t = np.array([x[0] for x in tr])
    return " ".join(f"{r[(t >= ts(y)) & (t < ts(y + 1))].mean():+.2f}" for y in range(y0, 2027))
def line(nm, tr, tg, f0=None):
    print("   годы", yrs(tr)); stats(nm, tr, f0 or ts(2022), tg)
if MOD == "emx":
    import pandas as pd, ema_h as E, mfeat
    from ema_core import outcomes
    d = E.d; side, tf, e200 = d.side.values, d.tf_s.values, d.s_d_ema200.values
    bema = pd.read_parquet(f"{E.D}/er_all.parquet", columns=["s_b_ema50"]).s_b_ema50.values
    LS = mfeat.at(d.sym.values, E.T - 3600)[:, mfeat.NAMES.index("ls_d24")] * side
    base = (side > 0) & (e200 < 10) & (tf != "4h") & (bema > 0) & ~(LS < 0.00314)
    for Y in (2022, 2023, 2024, 2025):   # the extra thresholds the same way as ema_h (the year before, 3 weeks gap)
        sc = E.S[str(Y)]; ref = (E.T >= ts(Y - 1)) & (E.T < ts(Y) - 21 * 86400)
        for q in (0.94, 0.95, 0.96): E.THR[Y][q] = float(np.quantile(sc[ref], q))
    def run(q, cap=12):
        idx = E.cand(q, base); R, K, KD = outcomes(idx, deep=0.2); tr = E.replay(idx, R, K, cap=cap)
        return [(int(E.T[i]), int(E.T[i] + K[i] * 3600), float(R[i]), 1, int(i)) for i in tr]
    print("=== EMA (v667) бот", flush=True)
    for q, cap in ((0.97, 12), (0.96, 12), (0.95, 12), (0.94, 12), (0.97, 20), (0.96, 20), (0.95, 20)):
        line(f"q{q}, лимит {cap}{' (сейчас)' if (q, cap) == (0.97, 12) else ''}", run(q, cap), 0.45)
    print("=== EMA проверка", flush=True)
    for q, cap in ((0.90, 12), (0.90, 20)): line(f"q{q}, лимит {cap}", run(q, cap), 0.50)
elif MOD == "cas":
    import cas_core as CX
    for q, nm, tg in ((0.995, "бот", 0.45), (0.98, "проверка", 0.50)):
        pass
    print("=== каскад", flush=True)
    for q, cap in ((0.995, 6), (0.99, 6), (0.995, 10), (0.99, 10), (0.98, 6)):
        line(f"q{q}, лимит {cap}{' (сейчас)' if (q, cap) == (0.995, 6) else ''}", CX.trades(q, cap=cap), 0.45 if q >= 0.99 else 0.50)
elif MOD == "nx":
    import nx_h as N
    from nx_x2 import build
    # thresholds q from the PREVIOUS year's out-of-sample scores (nx_sel keeps only 0.995 / 0.98)
    S = dict(N.S); T = N.T
    for s in (1, -1):
        sc = S[f"sc{s}"]
        for q in (0.995, 0.99, 0.985):
            th = np.full(len(T), np.inf, np.float32)
            for Y in (2023, 2024, 2025):
                ref = (T >= ts(Y - 1)) & (T < ts(Y)) & ~np.isnan(sc); te = (T >= ts(Y)) & (T < (ts(Y + 1) if Y < 2025 else ts(2027)))
                th[te] = np.quantile(sc[ref], q)
            S[f"tq{q}_{s}"] = th
    def cand(side, q, mask=None):
        sc = S[f"sc{side}"]; thr = S[f"t995_{side}"] if q == "orig" else S[f"tq{q}_{side}"]
        m = (sc >= thr) & ~np.isnan(sc) & (T >= ts(2023))
        if mask is not None: m &= mask
        return np.where(m)[0]
    N.cand = lambda side, q, mask=None: cand(side, q, mask)
    import nx_x2; nx_x2.N.cand = N.cand
    print("=== нейро (2023+, пороги по оценкам прошлого года)", flush=True)
    for q, cap in (("orig", 12), (0.995, 12), (0.99, 12), (0.985, 12), (0.99, 20)):
        line(f"q{q}, лимит {cap}{' (сейчас)' if q == 'orig' else ''}", sorted(build(q, cap=cap)), 0.45, ts(2023))
elif MOD == "rbx":
    import rb_h as B, mfeat
    from rb_x2 import run
    LS = mfeat.at(B.SYM, B.T + B.TF * 3600 - 3600)[:, mfeat.NAMES.index("ls_d24")] * B.SD
    OK = ~(LS > 0.0918)
    for nm, M, tg in (("бот", B.BOT, 0.45), ("проверка", B.CHECK, 0.50)):
        print(f"=== пробой (v667) {nm}", flush=True)
        for lab, kw in (("сейчас: сила 0.6, лимит 6", {}), ("лимит 8", dict(cap=8)), ("лимит 10", dict(cap=10)), ("сила ≥ 0.5", dict(min_brk=0.5)), ("сила ≥ 0.5, лимит 8", dict(min_brk=0.5, cap=8))):
            line(lab, run(M & OK, **kw), tg)
