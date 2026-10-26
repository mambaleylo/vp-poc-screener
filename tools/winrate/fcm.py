"""money: the opposite-side classic (rolling threshold) as a 6th module of the bundle as deployed (HTF on the 1d close now)"""
import numpy as np, json
exec(open("quiet1.py").read().split("for nm, dr, eng, mexpr, scf in CANDS:")[0].replace('H = rows("htf_bt_v1.json")', 'H = rows("htf_bt_v2_k24.json")'))
rec = roll2 >= ts(2024, 12)
def lst(fn):
    out = []
    for t in json.load(open(fn)):
        st_ = max(0.002, abs(t["e"] - t["sl"]) / t["e"]); out.append((float(t["t"]), float(t["x"]), float(t["r"]), st_, st_, 1.5, 5, cid(t["s"]), 1.0, 1e18))
    return np.array(out, float)
B2 = np.vstack([BASE, H]); ref2, _ = go(B2, [4.5, 3, 2.5, 2, 2.0, 0])
print(f"  сейчас (HTF по дню): 10% ${np.percentile(ref2, 10):,.0f} 25% ${np.percentile(ref2, 25):,.0f} медиана ${np.median(ref2):,.0f} 90% ${np.percentile(ref2, 90):,.0f} 2023-е ${np.median(ref2[q23]):,.0f}", flush=True)
for fn in ("fc_f_180_0.995.json", "fc_f_90_0.995.json"):
    X = lst(fn); print(fn, "сделок", len(X), "ср.R", round(X[:, 2].mean(), 3), flush=True)
    for rk in (1.0, 2.0):
        y, d = go(np.vstack([B2, X]), [4.5, 3, 2.5, 2, 2.0, rk]); q = y / ref2
        print(f"  {rk}%: 10% ${np.percentile(y, 10):>6,.0f} 25% ${np.percentile(y, 25):>6,.0f} медиана ${np.median(y):>7,.0f} 90% ${np.percentile(y, 90):>8,.0f} | 2023-е ${np.median(y[q23]):>6,.0f} | просадка {np.median(d)*100:.0f}% | окон лучше {np.mean(q > 1)*100:3.0f}% с дек.24 {np.mean(q[rec] > 1)*100:3.0f}% ×{np.median(q[rec]):.2f} худш ×{q.min():.2f}", flush=True)
