exec(open("pool2h.py").read().split("roll = np.arange")[0])
for nm, evs in (("4ч тень", W4), ("4ч + 2ч 2ATR", W4 + S2["2ч 2ATR"])):
    P = pool(evs); t0, t1, R, STv = P[:, 0], P[:, 1], P[:, 2], P[:, 3]
    yr = (t0 // 31557600 + 1970).astype(int)
    by = " ".join(f"{y}: {R[yr == y].mean():+.3f}R n{(yr == y).sum()}" for y in range(2022, 2027))
    fixed = []
    for st in ((2024, 1), (2024, 7), (2025, 1), (2025, 4), (2025, 7), (2025, 10)):
        s_ = ts(*st); v = sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0 if st < (2025, 10) else ts(2026, 10), 20, 0.04, -0.025)
        fixed.append(f"{st[0]}.{st[1]:02d}→ ${v[0]:,.0f} (dd {v[1]*100:.0f}%)")
    print(f"{nm:14s} [{by}]\n   старт $100, 4%, осторожно, 12 мес: " + " | ".join(fixed), flush=True)
