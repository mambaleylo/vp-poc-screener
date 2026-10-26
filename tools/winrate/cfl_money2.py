"""money: the bundle as deployed + 🔄 exit variants (the soft stop sizes the trade, the emergency stop counts in the open
risk cap); bot coins' list and the check coins' list; 1% / 2%"""
import numpy as np, json, sys
exec(open("cfl_lab4.py").read().rsplit('if __name__ == "__main__":', 1)[0])
from bt_trades import gate_sym
VAR = [("B 1 dATR, 4R, 96ч", {}), ("24ч 0.75/2, 4R", dict(sk=0.75, hard=2.0, ctf=24)), ("24ч 0.75/2, тейк 4 dATR", dict(sk=0.75, hard=2.0, ctf=24, take=4 / 0.75)),
       ("4ч 0.75/2, 4R", dict(sk=0.75, hard=2.0, ctf=4)), ("стоп 0.75 касанием, тейк 4 dATR", dict(sk=0.75, take=4 / 0.75))]
import os
if os.environ.get("CFL_VAR"): VAR = json.loads(os.environ["CFL_VAR"])
RKS = json.loads(os.environ.get("CFL_RK", "[1.0, 2.0]"))
lists = {}
for nm, kw in VAR:
    run4(nm, quiet=True, **kw); sb, rb, kb, sc_, rc, kc = OUT[nm]
    sk, hd = kw.get("sk", 1.0), kw.get("hard", 0.0) or kw.get("sk", 1.0)
    for grp, (s_, r_, k_) in (("бота", (sb, rb, kb)), ("контр.", (sc_, rc, kc))):
        X = np.array([(float(T[i] + 3600), float(T[i] + 3600 + k * 3600), float(r), max(0.002, sk * DA[i] / 100), max(0.002, hd * DA[i] / 100), 1.5, 5,
                       0, 1.0, 1e18) for i, r, k in zip(s_, r_, k_)], float)
        lists[(nm, grp)] = (X, [gate_sym(Dd["names"][SYM[i]])[0] for i in s_])
exec(open("fcm.py").read().split('for fn in ("fc_f_180_0.995.json"')[0])
for (nm, grp), (X, syms) in lists.items():
    X[:, 7] = [cid(s) for s in syms]
    for rk in RKS:
        y, d = go(np.vstack([B2, X]), [4.5, 3, 2.5, 2, 2.0, rk]); q = y / ref2
        A = np.vstack([B2, X]); A = A[np.argsort(A[:, 0], kind="stable")]; t0, t1, r_, st_, sth, buf, md, ci, wg, tbr = A.T
        l = sim6(t0, t1, np.where(md != 0, r_ - 0.03, r_), st_, sth, buf, md.astype(np.int64), ci.astype(np.int64), np.ones(6, np.bool_), np.array([4.5, 3, 2.5, 2, 2.0, rk]) / 100,
                 int(np.searchsorted(t0, ts(2025, 10))), ts(2026, 10), 0.05, wg, 10.0, 20.0, 0.9, 20.0, tbr)[0]
        print(f"  {nm:30s} {grp:6s} ({len(X)}, {X[:, 2].mean():+.2f}R) {rk}%: 10% ${np.percentile(y, 10):>6,.0f} медиана ${np.median(y):>7,.0f} 90% ${np.percentile(y, 90):>8,.0f}"
              f" | 2023-е ${np.median(y[q23]):>6,.0f} | 12 мес ${l:>8,.0f} | просадка {np.median(d)*100:.0f}% | окон лучше {np.mean(q > 1)*100:3.0f}% с дек.24 {np.mean(q[rec] > 1)*100:3.0f}% ×{np.median(q[rec]):.2f} худш ×{q.min():.2f}", flush=True)
