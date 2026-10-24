"""v0.99.695 (the chart's close, the emergency 3, the liquidation 1.25x): the risk % and the side cap with the bot's leverage"""
exec(open("closetf7.py").read().split("def money3")[0])
def money4(nm, P, hard, rk, cap=20):
    A = np.array([p[:5] for p in P], float); t0, t1, R, STv, K = A.T; STH = STv * hard / 2.0
    y = np.array([sim_125(t0, t1, R, STv, STH, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, cap, rk, -0.025) for s_ in roll])
    yh = np.array([sim_125(t0, t1, R, STv, STH, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, cap, rk, -0.04)[0] for s_ in roll])
    l12 = sim_125(t0, t1, R, STv, STH, int(np.searchsorted(t0, ts(2025, 10))), ts(2026, 10), cap, rk, -0.025)
    print(f"{nm:28s} медиана ${np.median(y[:, 0]):>6,.0f} 10% ${np.percentile(y[:, 0], 10):>5,.0f} просадка {np.median(y[:, 1])*100:.0f}% жёстко ${np.median(yh):,.0f} | 12 мес ${l12[0]:,.0f}", flush=True)
PC = pool(E, mk2(2.0, 3.0, lambda e: e["tfh"]))
for rk in (0.025, 0.03, 0.035, 0.04, 0.05, 0.06): money4(f"риск {rk*100:.1f}%", PC, 3.0, rk)
for cap in (15, 25, 30): money4(f"риск 4%, позиций {cap}", PC, 3.0, 0.04, cap)
