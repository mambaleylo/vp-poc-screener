exec(open("minnot697.py").read().split("for nm, minn in")[0])
for dep in (100, 150, 200, 500):
    minn = 5.0 / dep
    Y = np.array([sim3(t0, t1, R, STv, STH, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.025, minn) for s_ in roll])
    l12 = sim3(t0, t1, R, STv, STH, int(np.searchsorted(t0, ts(2025, 10))), ts(2026, 10), 20, 0.04, -0.025, minn)
    n = Y[:, 2] + Y[:, 3] + Y[:, 4]; k = dep / 100.0
    print(f"старт ${dep}: медиана ${np.median(Y[:, 0]) * k:,.0f} 10% ${np.percentile(Y[:, 0], 10) * k:,.0f} просадка {np.median(Y[:, 1])*100:.0f}% | 12 мес ${l12[0] * k:,.0f} | пропущено {np.median(Y[:, 4] / n)*100:.0f}% (x{np.median(Y[:, 0]) * k / 4855:.2f} к $100)", flush=True)
