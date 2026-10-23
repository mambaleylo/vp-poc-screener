"""lab after v0.99.689: the two best third streams (2h wick 1 ATR, 1h close 2 ATR28) alone, as a third and both as a
third + fourth; by year, the money from fixed starts with the drawdown"""
exec(open("pool3s.py").read().split("\nroll = np.arange")[0])
roll = np.arange(ts(2024), ts(2025, 10) + 1, 7 * 86400.0)
W2 = C3["2ч тень 1ATR"](); H1 = C3["1ч закр 2ATR28"]()
def show(nm, evs):
    P = pool(evs); t0, t1, R, STv = P[:, 0], P[:, 1], P[:, 2], P[:, 3]
    y = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.025) for s_ in roll])
    yh = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.04)[0] for s_ in roll])
    yr = (t0 // 31557600 + 1970).astype(int)
    by = " ".join(f"{y_}:{R[yr == y_].mean():+.2f}/{(yr == y_).sum()}" for y_ in range(2022, 2027))
    fx = []
    for st in ((2024, 1), (2024, 7), (2025, 1), (2025, 4), (2025, 7), (2025, 10)):
        s_ = ts(*st); v = sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0 if st < (2025, 10) else ts(2026, 10), 20, 0.04, -0.025)
        fx.append(f"{st[0] % 100}.{st[1]:02d}→${v[0]:,.0f}({v[1]*100:.0f}%)")
    print(f"{nm:30s} n{len(R)} {R.mean():+.3f}R [{by}] | медиана ${np.median(y[:, 0]):,.0f} 10% ${np.percentile(y[:, 0], 10):,.0f} "
          f"просадка {np.median(y[:, 1])*100:.0f}%/{np.percentile(y[:, 1], 90)*100:.0f}% | жёстко ${np.median(yh):,.0f}\n    " + " ".join(fx), flush=True)
show("2ч тень 1ATR одна", W2); show("1ч закр 2ATR28 одна", H1)
show("4ч + 2ч закр (сейчас)", W4 + C2)
show("+ 2ч тень", W4 + C2 + W2); show("+ 1ч закр", W4 + C2 + H1); show("+ 2ч тень + 1ч закр", W4 + C2 + W2 + H1)
show("4ч + 2ч тень (без 2ч закр)", W4 + W2); show("4ч + 1ч закр (без 2ч)", W4 + H1)
