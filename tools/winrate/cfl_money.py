"""money: the bundle as deployed (HTF on the 1d close) + 🔄 variants (bot coins; and the check coins' list) at 1 / 2%"""
import numpy as np, json
src = open("cfl_lab.py").read().split('if __name__ == "__main__":')[0].replace("@njit(cache=True)", "@njit")
src = src.replace("        res.append((sel, r, y))", "        res.append((sel, r, y)); LAST[grp] = [(int(i), float(R[i]), int(K[i])) for i in sel]")
exec(src); LAST = {}
from bt_trades import gate_sym
lists = {}
for nm, kw in (("B0", {}), ("L96", dict(side=1, hold=96)), ("L96C20", dict(side=1, hold=96, cap=20)), ("L96T4C20", dict(side=1, hold=96, take=4.0, cap=20))):
    run(nm, quiet=True, **kw)
    for grp in (True, False):
        out = []
        for i, r, k in LAST[grp]:
            t0 = int(T[i]) + 3600; st_ = float(DA[i]) / 100
            out.append({"s": gate_sym(Dd["names"][SYM[i]])[0], "t": t0, "x": t0 + k * 3600, "e": 1.0, "sl": 1.0 - st_, "r": r})
        lists[(nm, grp)] = out
exec(open("fcm.py").read().split('for fn in ("fc_f_180_0.995.json"')[0])
def lst2(L):
    return np.array([(float(t["t"]), float(t["x"]), float(t["r"]), max(0.002, 1 - t["sl"]), max(0.002, 1 - t["sl"]), 1.5, 5, cid(t["s"]), 1.0, 1e18) for t in L], float)
def money(nm, X, rk):
    A = np.vstack([B2, X]); y, d = go(A, [4.5, 3, 2.5, 2, 2.0, rk]); q = y / ref2
    A = A[np.argsort(A[:, 0], kind="stable")]; t0, t1, r_, st_, sth, buf, md, ci, wg, tbr = A.T
    l = sim6(t0, t1, np.where(md != 0, r_ - 0.03, r_), st_, sth, buf, md.astype(np.int64), ci.astype(np.int64), np.ones(6, np.bool_), np.array([4.5, 3, 2.5, 2, 2.0, rk]) / 100,
             int(np.searchsorted(t0, ts(2025, 10))), ts(2026, 10), 0.05, wg, 10.0, 20.0, 0.9, 20.0, tbr)[0]
    print(f"  {nm:28s} {rk}%: 10% ${np.percentile(y, 10):>6,.0f} 25% ${np.percentile(y, 25):>6,.0f} медиана ${np.median(y):>7,.0f} 90% ${np.percentile(y, 90):>8,.0f} | 2023-е ${np.median(y[q23]):>6,.0f} | 12 мес ${l:>8,.0f} | окон лучше {np.mean(q > 1)*100:3.0f}% с дек.24 {np.mean(q[rec] > 1)*100:3.0f}% ×{np.median(q[rec]):.2f} худш ×{q.min():.2f}", flush=True)
for (nm, grp), L in lists.items():
    X = lst2(L)
    for rk in (1.0, 2.0): money(f"{nm} {'бота' if grp else 'контр.'} ({len(X)}, {X[:, 2].mean():+.2f}R)", X, rk)
