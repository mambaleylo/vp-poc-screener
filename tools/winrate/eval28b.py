"""the models retrained on the v0.99.692 exit labels (s28) vs the deployed ones (s26): the 4h + 2h pool in the honest order
with the v0.99.695 exits (the chart candle's close, the emergency 3) and the bot's leverage (the liquidation 1.25x)"""
exec(open("closetf7.py").read().split("def money3")[0])
def money5(nm, evs):
    P = pool(evs, mk2(2.0, 3.0, lambda e: e["tfh"]))
    A = np.array([p[:5] for p in P], float); t0, t1, R, STv, K = A.T; STH = STv * 1.5
    y = np.array([sim_125(t0, t1, R, STv, STH, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.025) for s_ in roll])
    yh = np.array([sim_125(t0, t1, R, STv, STH, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.04)[0] for s_ in roll])
    l12 = sim_125(t0, t1, R, STv, STH, int(np.searchsorted(t0, ts(2025, 10))), ts(2026, 10), 20, 0.04, -0.025)
    yrs = (t0.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970)
    ys = " ".join(f"{Y % 100}:{R[yrs == Y].mean():+.2f}" for Y in range(2022, 2027))
    print(f"{nm:44s} n{len(R):5d} WR {np.mean(K == 1)*100:.0f}% {R.mean():+.3f}R | медиана ${np.median(y[:, 0]):>6,.0f} 10% ${np.percentile(y[:, 0], 10):>5,.0f} просадка {np.median(y[:, 1])*100:.0f}% жёстко ${np.median(yh):,.0f} | 12 мес ${l12[0]:,.0f} | {ys}", flush=True)
    return y[:, 0]
for nm, f4, f2 in (("развёрнутые (s26)", "s26_s23_4h_w1_0.npz", "s26_s21h2_d2_1.npz"), ("переобученные на выход 692 (s28)", "s28_s23_4h_w1.npz", "s28_s21h2_d2.npz")):
    for q in (0.99, 0.995):
        e4 = events3("s23_4h", 2, f4, "s23_engine", 4, "wick", 1.0, q); e2 = events3("s21h2", 0, f2, "s21h2_engine", 2, "close", 2.0, q)
        money5(f"{nm} q{q}: 4ч+2ч", e4 + e2)
