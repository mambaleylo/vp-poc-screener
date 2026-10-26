"""the header's bad year (p10 of the 12-month windows from $100): which starts, what breaks there; then the levers:
all risks scaled, a drawdown throttle (risk x f while the equity is > a below its peak), the open-risk cap, ⚡'s cap.
The bundle as deployed (⚡ 4.5, P/R 3, SMC 2.5, EMA 2, HTF 2), friction -0.03R a trade."""
import numpy as np, warnings; warnings.filterwarnings("ignore")
exec(open("htf_money5.py").read().split("L = [(k")[0])
s2 = src.replace(", HMAX, DCAP, TBR):", ", HMAX, DCAP, TBR, DDA, DDF):").replace("def simx(", "def simd(")
s2 = s2.replace("ru = eq * risk[MD[j]] * WGT[j]\n", "ru = eq * risk[MD[j]] * WGT[j]\n        if DDA > 0 and eq < peak * (1 - DDA): ru *= DDF\n", 1)
assert "DDA > 0 and eq < peak" in s2
exec(s2)
A = np.vstack([BASE, rows("htf_bt_v1.json")]); A = A[np.argsort(A[:, 0], kind="stable")]
t0, t1, r0, st_, sth, buf, md, ci, wg, tbr = A.T; md = md.astype(np.int64); ci = ci.astype(np.int64); r_ = np.where(md != 0, r0 - 0.03, r0)
use = np.ones(5, np.bool_); RK = np.array([4.5, 3, 2.5, 2, 2.0])
def go(sc=1.0, hmax=0.9, dcap=20.0, dda=0.0, ddf=1.0, rk=None):
    rk_ = (RK if rk is None else np.array(rk)) * sc / 100
    f = lambda a, b: simd(t0, t1, r_, st_, sth, buf, md, ci, use, rk_, int(np.searchsorted(t0, a)), b, 0.05, wg, 10.0, 20.0, hmax, dcap, tbr, dda, ddf)
    return [f(s_, s_ + 365 * 86400.0) for s_ in roll2]
Y = go(); y = np.array([v[0] for v in Y]); dd = np.array([v[1] for v in Y])
print(f"как сейчас: 10% ${np.percentile(y, 10):,.0f} 25% ${np.percentile(y, 25):,.0f} медиана ${np.median(y):,.0f} 90% ${np.percentile(y, 90):,.0f} | просадка мед {np.median(dd)*100:.0f}% | ≥$15k за год {np.mean(y >= 15000)*100:.0f}% | худшее ${y.min():,.0f}", flush=True)
o = np.argsort(y)[:max(1, len(y) // 10)]
print("== худшие 10% стартов:")
for i in o:
    v = Y[i]; d = np.datetime64(int(roll2[i]), "s").astype("datetime64[D]")
    print(f"   старт {d}: итог ${v[0]:>6,.0f} просадка {v[1]*100:.0f}% | сделок {v[2].astype(int).tolist()} | $ по модулям ⚡/PR/SMC/EMA/HTF {np.round(v[3]).astype(int).tolist()}", flush=True)
def line(nm, **kw):
    Y = go(**kw); y2 = np.array([v[0] for v in Y]); d2 = np.array([v[1] for v in Y]); q = y2 / y
    print(f"  {nm:34s} 10% ${np.percentile(y2, 10):>6,.0f} 25% ${np.percentile(y2, 25):>6,.0f} медиана ${np.median(y2):>7,.0f} 90% ${np.percentile(y2, 90):>8,.0f} | просадка {np.median(d2)*100:.0f}% (90%: {np.percentile(d2, 90)*100:.0f}%) | ≥$15k {np.mean(y2 >= 15000)*100:3.0f}% | худшее ${y2.min():>5,.0f} | окон лучше {np.mean(q > 1)*100:3.0f}%", flush=True)
print("== весь риск ×k")
for k in (0.6, 0.7, 0.8, 0.9, 1.1): line(f"риск ×{k}", sc=k)
print("== просадка → риск меньше")
for a in (0.3, 0.4, 0.5):
    for f_ in (0.5, 0.7): line(f"просадка >{int(a*100)}% → риск ×{f_}", dda=a, ddf=f_)
print("== потолок открытого риска / лимит ⚡")
for h in (0.6, 0.7, 0.8): line(f"открытый риск ≤ {int(h*100)}%", hmax=h)
for dc in (10, 15): line(f"⚡ не больше {dc} сразу", dcap=float(dc))
print("== риск по модулям")
line("⚡ 4 остальные как есть", rk=[4.0, 3, 2.5, 2, 2.0])
line("⚡ 4.5, P/R 2", rk=[4.5, 2, 2.5, 2, 2.0])
line("⚡ 4.5, SMC 2, EMA 1.5", rk=[4.5, 3, 2.0, 1.5, 2.0])
