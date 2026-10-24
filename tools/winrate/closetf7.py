"""the margin is the binder: the bot's leverage keeps the liquidation at 1.5x the exchange stop's distance. With the
buffer 1.25x / 1.15x (the same for every rule) — the touch stop vs the chart's close, money with the bot's leverage"""
exec(open("closetf6.py").read().split("def by_q")[0])
src = open("closetf4.py").read(); src = "@njit\ndef sim2" + src.split("@njit\ndef sim2")[1].split("\ndef money2")[0]
for sm in (1.25, 1.15):
    exec(src.replace("def sim2", f"def sim_{round(sm*100)}").replace("1.5 * STH[j]", f"{sm} * STH[j]"))
def money3(nm, P, hard, simf):
    A = np.array([p[:5] for p in P], float); t0, t1, R, STv, K = A.T; STH = STv * hard / 2.0
    y = np.array([simf(t0, t1, R, STv, STH, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.025) for s_ in roll])
    l12 = simf(t0, t1, R, STv, STH, int(np.searchsorted(t0, ts(2025, 10))), ts(2026, 10), 20, 0.04, -0.025)
    q = " · ".join(f"{Y % 100}.{M:02d}: ${simf(t0, t1, R, STv, STH, int(np.searchsorted(t0, ts(Y, M))), min(ts(Y, M) + 365 * 86400.0, ts(2026, 10)), 20, 0.04, -0.025)[0]:,.0f}"
                   for Y, M in [(2024, 1), (2024, 4), (2024, 7), (2024, 10), (2025, 1), (2025, 4), (2025, 7)])
    print(f"{nm:34s} медиана ${np.median(y[:, 0]):>6,.0f} 10% ${np.percentile(y[:, 0], 10):>5,.0f} просадка {np.median(y[:, 1])*100:.0f}% | 12 мес ${l12[0]:,.0f} | {q}", flush=True)
PT = pool(E, mk3(1.1, 2.0, 2.0)); PC = pool(E, mk2(2.0, 3.0, lambda e: e["tfh"]))
for sm, f in ((1.25, sim_125), (1.15, sim_115)):
    print(f"== запас до ликвидации {sm}x стопа")
    money3("стоп касанием 2, тейк 1.1", PT, 2.0, f)
    money3("закр. свечи графика, авар. 3", PC, 3.0, f)
