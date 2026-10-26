"""the opposite-side classic: per indicator, money at the grid's points, the entry slippage stress, the check coins'
list as the module; events < 90 days after the coin's listing dropped (the engine needs 90 days live)"""
import numpy as np, json
exec(open("fcm.py").read().split('for fn in ("fc_f_180_0.995.json"')[0])
import lv_engine as LE, ev3_engine as E3
from bt_trades import gate_sym
sp = json.load(open("lv/split.json")); inv = {gate_sym(s)[0]: s for s in sp["bot"] + sp["chk"]}
T0 = {}
def age_ok(p):
    s = inv[p["s"]]
    if s not in T0: T0[s] = int(LE.load_np(s)[0][0])
    return p["t"] - T0[s] >= 90 * 86400
def lst(fn, extra=0.0):
    out = []
    for t in json.load(open(fn)):
        if not age_ok(t): continue
        st_ = max(0.002, abs(t["e"] - t["sl"]) / t["e"]); out.append((float(t["t"]), float(t["x"]), float(t["r"]) - extra, st_, st_, 1.5, 5, cid(t["s"]), 1.0, 1e18))
    return np.array(out, float)
P = [p for p in json.load(open("fc_f_180_0.995.json")) + json.load(open("fc_f_180_0.995_chk.json")) if age_ok(p)]
print("== по индикаторам (180д q0.995, бот+контр.)")
for f in range(len(E3.FAMS)):
    r = np.array([p["r"] for p in P if p["fam"] == f])
    if len(r): print(f"   {E3.FAMS[f]:12s} сделок {len(r):3d} {r.mean():+.2f}R WR {np.mean(r > 0)*100:.0f}%")
def money(nm, X, rk=2.0):
    A = np.vstack([B2, X]); y, d = go(A, [4.5, 3, 2.5, 2, 2.0, rk]); q = y / ref2
    A = A[np.argsort(A[:, 0], kind="stable")]; t0, t1, r_, st_, sth, buf, md, ci, wg, tbr = A.T
    l = sim6(t0, t1, np.where(md != 0, r_ - 0.03, r_), st_, sth, buf, md.astype(np.int64), ci.astype(np.int64), np.ones(6, np.bool_), np.array([4.5, 3, 2.5, 2, 2.0, rk]) / 100,
             int(np.searchsorted(t0, ts(2025, 10))), ts(2026, 10), 0.05, wg, 10.0, 20.0, 0.9, 20.0, tbr)[0]
    print(f"  {nm:34s} {rk}%: 10% ${np.percentile(y, 10):>6,.0f} 25% ${np.percentile(y, 25):>6,.0f} медиана ${np.median(y):>7,.0f} 90% ${np.percentile(y, 90):>8,.0f} | 2023-е ${np.median(y[q23]):>6,.0f} | 12 мес ${l:>8,.0f} | окон лучше {np.mean(q > 1)*100:3.0f}% с дек.24 {np.mean(q[rec] > 1)*100:3.0f}% ×{np.median(q[rec]):.2f} худш ×{q.min():.2f}", flush=True)
print("== деньги (монеты бота)")
for D, qq in ((120, 0.995), (180, 0.993), (180, 0.995), (180, 0.997), (240, 0.995), (240, 0.997)):
    X = lst(f"fc_f_{D}_{qq}.json"); money(f"{D}д q{qq} ({len(X)} сделок, {X[:, 2].mean():+.2f}R)", X)
print("== стресс входа по рынку (180д q0.995)")
for ex in (0.05, 0.10): money(f"проскальзывание −{ex}R на сделку", lst("fc_f_180_0.995.json", ex))
print("== контрольные монеты вместо монет бота (180д q0.995)")
X = lst("fc_f_180_0.995_chk.json"); money(f"контрольные ({len(X)} сделок, {X[:, 2].mean():+.2f}R)", X)
money(f"контрольные ({len(X)} сделок)", X, 1.0)
