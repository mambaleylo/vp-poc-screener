"""lab: the stop's size with the v0.99.690 take — a grid (stop x the dip n x the near take), by year and the last 12 months"""
exec(open("exit2.py").read().split('\nshow("СЕЙЧАС')[0])
def show3(nm, **kw):
    p = dict(BASE, **kw); P = run2(p); t0, t1, R, STv, K = P[:, 0], P[:, 1], P[:, 2], P[:, 3], P[:, 4]
    y = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.025) for s_ in roll])
    yh = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.04)[0] for s_ in roll])
    yr = (t0 // 31557600 + 1970).astype(int); h = t0 >= ts(2025, 10)
    by = " ".join(f"{y_ % 100}:{R[yr == y_].mean():+.2f}" for y_ in range(2022, 2027))
    l12 = sim(t0, t1, R, STv, int(np.searchsorted(t0, ts(2025, 10))), ts(2026, 10), 20, 0.04, -0.025)
    l12h = sim(t0, t1, R, STv, int(np.searchsorted(t0, ts(2025, 10))), ts(2026, 10), 20, 0.04, -0.04)
    print(f"{nm:34s} {R.mean():+.3f}R WR {np.isin(K, (1, 2)).mean()*100:.0f}% [{by}] посл.12м {R[h].mean():+.3f}R ${l12[0]:,.0f} (жёстко ${l12h[0]:,.0f}, просадка {l12[1]*100:.0f}%) | "
          f"медиана ${np.median(y[:, 0]):,.0f} 10% ${np.percentile(y[:, 0], 10):,.0f} хуже всех ${y[:, 0].min():,.0f} просадка {np.median(y[:, 1])*100:.0f}%/{np.percentile(y[:, 1], 90)*100:.0f}% | жёстко ${np.median(yh):,.0f}", flush=True)
for stp in (2.0, 1.75, 1.5, 1.25, 1.0):
    for n in (0.3, 0.4, 0.5):
        show3(f"стоп {stp}, откат {n}", stp=stp, n=n)
    show3(f"стоп {stp}, откат 0.4, после отката 0.75", stp=stp, tkn=0.75)
