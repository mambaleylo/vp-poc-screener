"""⚡ pool: R by the stop's size (2 ATR / price — the coin's volatility on the chart) and by the stream, by year"""
exec(open("port_expect2.py").read().split("A = np.array(sorted(rows)")[0])
st = np.array([float(p[3]) for p in PC]); R = np.array([float(p[2]) for p in PC]); t0 = np.array([float(p[0]) for p in PC])
tfh = np.array([p[5]["tfh"] for p in PC]); Y = t0.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970
q = np.quantile(st, [0.2, 0.4, 0.6, 0.8]); g = np.digitize(st, q)
print("стоп % квинтили", (q * 100).round(2))
for k in range(5):
    m = g == k; print(f"q{k+1} стоп ~{np.median(st[m])*100:.1f}% {R[m].mean():+.3f}R ({m.sum()}) | " + " ".join(f"{R[m & (Y == y)].mean():+.2f}" for y in range(2022, 2027)))
for h in (4, 2):
    m = tfh == h; print(f"поток {h}ч {R[m].mean():+.3f}R ({m.sum()}) | " + " ".join(f"{R[m & (Y == y)].mean():+.2f}" for y in range(2022, 2027)))
