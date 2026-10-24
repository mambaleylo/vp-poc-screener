"""the bundle with v0.99.704 rules: the year's multiplier from a $100 vs a $1000 start ($5 minimum = 0.05 vs 0.005 of the start)"""
exec(open("port_osc3.py").read().split('print("медиана wt')[0])
w = W_abs(-3, 22)
use = np.array([1, 1, 1, 1], np.bool_); rk = np.array([4, 2, 1, 0.5]) / 100
for start, minn in ((100, 0.05), (1000, 0.005)):
    Y = [simp(T0, T1, R, ST, STH, BUF, MD, CID, use, rk, int(np.searchsorted(T0, s_)), s_ + 365 * 86400.0, minn, w) for s_ in roll2]
    y = np.array([v[0] for v in Y]) / 100; dd = np.array([v[1] for v in Y])
    print(f"старт ${start}: множитель за год 10% x{np.percentile(y, 10):.1f} медиана x{np.median(y):.1f} 90% x{np.percentile(y, 90):.1f} · худший x{y.min():.1f} · просадка медиана {np.median(dd)*100:.0f}%, худшая {dd.max()*100:.0f}%")
# two years in a row: the second year's multiplier right after a weak first one (the bottom 25% of the starts)
y1 = np.array([simp(T0, T1, R, ST, STH, BUF, MD, CID, use, rk, int(np.searchsorted(T0, s_)), s_ + 365 * 86400.0, 0.005, w)[0] / 100 for s_ in roll2])
pairs = [(y1[i], y1[i + 52]) for i in range(len(roll2) - 52)]
weak = [b for a, b in pairs if a <= np.percentile(y1, 25)]
print("после слабого года (нижние 25%) следующий год: 10%", round(np.percentile(weak, 10), 1), "медиана", round(np.median(weak), 1), "из", len(weak))
