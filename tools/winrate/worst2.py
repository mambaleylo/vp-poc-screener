exec(open("worst1.py").read().split('o = np.argsort(y)')[0])
def line(nm, **kw):
    Y = go(**kw); y2 = np.array([v[0] for v in Y]); d2 = np.array([v[1] for v in Y]); q = y2 / y
    rec = roll2 >= ts(2024, 12)
    print(f"  {nm:30s} 10% ${np.percentile(y2, 10):>6,.0f} 25% ${np.percentile(y2, 25):>6,.0f} медиана ${np.median(y2):>7,.0f} 90% ${np.percentile(y2, 90):>8,.0f} | просадка {np.median(d2)*100:.0f}% (90%: {np.percentile(d2, 90)*100:.0f}%) | ≥$15k {np.mean(y2 >= 15000)*100:3.0f}% | окон лучше {np.mean(q > 1)*100:3.0f}% с дек.24 {np.mean(q[rec] > 1)*100:3.0f}% ×{np.median(q[rec]):.2f}", flush=True)
for dc in (6, 8, 10, 12):
    line(f"⚡ ≤{dc}", dcap=float(dc))
    line(f"⚡ ≤{dc}, ⚡ 5%", dcap=float(dc), rk=[5.0, 3, 2.5, 2, 2.0])
    line(f"⚡ ≤{dc}, ⚡ 5.5%", dcap=float(dc), rk=[5.5, 3, 2.5, 2, 2.0])
