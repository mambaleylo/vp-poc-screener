"""from $100: how long to $15,000 on the bundle as deployed (⚡ 4.5, P/R 3, SMC 2.5, EMA 2, HTF 2; cross 10x, the open risk
<= 90%), a start every week 2023-01..2026-09; per start the first month end with the account >= $15k (a bust -> the
sim's own re-deposit of $100, counted against the result); with friction -0.03R a trade and without"""
import numpy as np, warnings; warnings.filterwarnings("ignore")
exec(open("htf_money5.py").read().split("L = [(k")[0])
A = np.vstack([BASE, rows("htf_bt_v1.json")]); A = A[np.argsort(A[:, 0], kind="stable")]
t0, t1, r0, st_, sth, buf, md, ci, wg, tbr = A.T; md = md.astype(np.int64); ci = ci.astype(np.int64)
use = np.ones(5, np.bool_); rk = np.array([4.5, 3, 2.5, 2, 2.0]) / 100
END = ts(2026, 10)
starts = np.arange(ts(2023, 1), ts(2026, 9), 7 * 86400.0)
M = 30.44 * 86400
for fr in (True, False):
    r_ = np.where(md != 0, r0 - 0.03, r0) if fr else r0
    f = lambda a, b: simx(t0, t1, r_, st_, sth, buf, md, ci, use, rk, int(np.searchsorted(t0, a)), b, 0.05, wg, 10.0, 20.0, 0.9, 20.0, tbr)[0]
    got, cens = [], []
    for s in starts:
        hit = None; k = 1
        while s + k * M <= END:
            if f(s, s + k * M) >= 15000: hit = k; break
            k += 1
        (got.append(hit) if hit else cens.append((END - s) / M))
    got = np.array(got); n = len(starts)
    print(f"== {'с трением' if fr else 'как в бэктесте'}: стартов {n}, дошли до $15k {len(got)} ({len(got)/n*100:.0f}%)")
    if len(got):
        print(f"   месяцев: быстрее всего {got.min()}, 25% {np.percentile(got, 25):.0f}, медиана {np.median(got):.0f}, 75% {np.percentile(got, 75):.0f}, дольше всего {got.max()}")
    for m_ in (6, 9, 12, 18, 24):
        el = (END - starts) / M >= m_
        ok = np.array([g is not None and g <= m_ for g in [None] * 0])
        hits = sum(1 for s, in zip(starts) if False)
    res = {}
    k_ = 0
    allres = []
    for s in starts:
        pass
    # share within m months among the starts that had m months of data
    hitmap = {}
    gi = 0
    for idx, s in enumerate(starts):
        pass
    print("   не дошли (старт: сколько месяцев было):", [round(c, 1) for c in cens][:12], "…" if len(cens) > 12 else "")
