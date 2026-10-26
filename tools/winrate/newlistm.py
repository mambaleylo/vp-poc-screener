"""money: the new-listing short as a 6th module of the bundle as deployed (friction -0.03R)"""
import numpy as np, json
exec(open("quiet1.py").read().split("for nm, dr, eng, mexpr, scf in CANDS:")[0])
def lst(fn):
    out = []
    for t in json.load(open(fn)):
        st_ = max(0.002, abs(t["e"] - t["sl"]) / t["e"]); out.append((float(t["t"]), float(t["x"]), float(t["r"]), st_, st_, 1.5, 5, cid(t["s"]), 1.0, 1e18))
    return np.array(out, float)
rec = roll2 >= ts(2024, 12)
for fn in ("newlist_3_14_2.0.json", "newlist_5_14_2.0.json", "newlist_7_14_2.0.json"):
    X = lst(fn); print(fn, "сделок", len(X), "ср.R", round(X[:, 2].mean(), 3), flush=True)
    for rk in (0.5, 1.0, 2.0):
        y, d = go(np.vstack([B, X]), [4.5, 3, 2.5, 2, 2.0, rk]); q = y / ref
        print(f"  {rk}%: 10% ${np.percentile(y, 10):>6,.0f} 25% ${np.percentile(y, 25):>6,.0f} медиана ${np.median(y):>7,.0f} 90% ${np.percentile(y, 90):>8,.0f} | 2023-е мед ${np.median(y[q23]):>6,.0f} | просадка {np.median(d)*100:.0f}% | окон лучше {np.mean(q > 1)*100:3.0f}% с дек.24 {np.mean(q[rec] > 1)*100:3.0f}% ×{np.median(q[rec]):.2f} худш ×{q.min():.2f}", flush=True)
