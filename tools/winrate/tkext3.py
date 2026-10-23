"""the take extension (tkext.py) with and without the third stream (2h wick 1 ATR); by year and from fixed starts"""
exec(open("tkext.py").read().split("\nBARS = {}")[0])
BARS = {}
EVA = events("s23_4h", 2, "s26_s23_4h_w1_0.npz", "s23_engine", 4, "wick", 1.0) + events("s21h2", 0, "s26_s21h2_d2_1.npz", "s21h2_engine", 2, "close", 2.0)
EVB = events("s21h2", 2, "s26_s21h2_wick1_1.npz", "s21h2_engine", 2, "wick", 1.0)
exec("@njit\ndef ex" + open("tkext.py").read().split("@njit\ndef ex")[1].split("\nroll = np.arange")[0])
roll = np.arange(ts(2024), ts(2025, 10) + 1, 7 * 86400.0)
def show(nm, n, e):
    P = run(n, e, 0); t0, t1, R, STv, K = P[:, 0], P[:, 1], P[:, 2], P[:, 3], P[:, 4]
    y = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.025) for s_ in roll])
    yh = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.04)[0] for s_ in roll])
    yr = (t0 // 31557600 + 1970).astype(int)
    by = " ".join(f"{y_}:{R[yr == y_].mean():+.2f}" for y_ in range(2022, 2027))
    fx = []
    for st in ((2024, 1), (2024, 7), (2025, 1), (2025, 4), (2025, 7), (2025, 10)):
        s_ = ts(*st); v = sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0 if st < (2025, 10) else ts(2026, 10), 20, 0.04, -0.025)
        fx.append(f"{st[0] % 100}.{st[1]:02d}→${v[0]:,.0f}({v[1]*100:.0f}%)")
    m6 = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 182 * 86400.0, 20, 0.04, -0.025)[0] for s_ in roll])
    print(f"{nm:34s} n{len(R)} {R.mean():+.3f}R WR {np.isin(K, (1, 2)).mean()*100:.0f}% [{by}] | медиана ${np.median(y[:, 0]):,.0f} 10% ${np.percentile(y[:, 0], 10):,.0f} "
          f"просадка {np.median(y[:, 1])*100:.0f}%/{np.percentile(y[:, 1], 90)*100:.0f}% | жёстко ${np.median(yh):,.0f} | 6 мес ниже $100: {(m6 < 100).mean()*100:.0f}%\n    " + " ".join(fx), flush=True)
for lab, EVx in (("4ч + 2ч закр", EVA), ("+ 2ч тень", EVA + EVB)):
    EV = EVx
    for nm, n, e in (("тейк 1 ATR (сейчас)", 0, 0), ("n=0.4 → тейк 2 ATR", 0.4, 1.0), ("n=0.5 → тейк 2 ATR", 0.5, 1.0)):
        show(f"{lab}: {nm}", n, e)
