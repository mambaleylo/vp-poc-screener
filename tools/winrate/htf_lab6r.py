"""📏 HTF round 6 — the room in the bundle: the risks of ⚡ and HTF, the open-risk cap (HMAX), with friction; vs the deployed
(⚡ 4.5, P/R 3, SMC 2.5, EMA 2, HTF 1.5, HMAX 0.9): windows, the last 12 months, trims / skips, the worst moment"""
import numpy as np, warnings, json, itertools; warnings.filterwarnings("ignore")
exec(open("htf_money5.py").read().split("L = [(k")[0])
H = rows("htf_bt_v1.json")
A = np.vstack([BASE, H]); A = A[np.argsort(A[:, 0], kind="stable")]
t0, t1, r_, st_, sth, buf, md, ci, wg, tbr = A.T; md = md.astype(np.int64); ci = ci.astype(np.int64); r_ = np.where(md != 0, r_ - 0.03, r_)
use = np.ones(5, np.bool_)
def go(rk, hmax):
    rk_ = np.array(rk, float) / 100
    f = lambda a, b: simx(t0, t1, r_, st_, sth, buf, md, ci, use, rk_, int(np.searchsorted(t0, a)), b, 0.05, wg, 10.0, 20.0, hmax, 20.0, tbr)
    Y = [f(s_, s_ + 365 * 86400.0) for s_ in roll2]
    return np.array([v[0] for v in Y]), np.array([v[1] for v in Y]), f(ts(2025, 10), ts(2026, 10)), np.array([v[7] for v in Y])
ref, rdd, rl, rw = go([4.5, 3, 2.5, 2, 1.5], 0.9)
print(f"бот сейчас: медиана ${np.median(ref):,.0f} 10% ${np.percentile(ref, 10):,.0f} просадка {np.median(rdd)*100:.0f}% | 12 мес ${rl[0]:,.0f} | сделок {rl[2].astype(int).tolist()} урезано {rl[4]} пропущено {rl[5]} из {rl[6]} | худший момент мед {np.median(rw)*100:.0f}%", flush=True)
noh, _, nl, _ = go([4.5, 3, 2.5, 2, 0], 0.9)
print(f"без HTF: 12 мес урезано {nl[4]} пропущено {nl[5]} из {nl[6]}", flush=True)
for hmax in (0.9, 1.0, 1.2):
    for dl, hr in itertools.product((3.5, 4.0, 4.5), (1.5, 2.0, 2.5, 3.0)):
        if (dl, hr, hmax) == (4.5, 1.5, 0.9): continue
        y, dd, l, w = go([dl, 3, 2.5, 2, hr], hmax); q = y / ref
        print(f"  ⚡{dl} HTF{hr} HMAX{hmax}: медиана ${np.median(y):>7,.0f} 10% ${np.percentile(y, 10):>6,.0f} просадка {np.median(dd)*100:.0f}% (90%: {np.percentile(dd, 90)*100:.0f}%) | 12 мес ${l[0]:>8,.0f} | окон лучше {np.mean(q > 1)*100:3.0f}% ×{np.median(q):.2f} с дек.24 {np.mean(q[recent] > 1)*100:3.0f}% ×{np.median(q[recent]):.2f} худш ×{q.min():.2f} | урезано {l[4]} пропущ {l[5]} | худший момент {np.median(w)*100:.0f}%", flush=True)
