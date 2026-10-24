"""closetf5 follow-up (the bot's leverage): the emergency stop nearer (2.5 / 2.75 — more leverage, less margin), and the
money by the window's start (quarters) for the touch stop vs the chart's close"""
exec(open("closetf5.py").read().split("r_t = money2(")[0])
def by_q(nm, P, hard):
    A = np.array([p[:5] for p in P], float); t0, t1, R, STv, K = A.T; STH = STv * hard / 2.0
    out = []
    for Y, M in [(2024, 1), (2024, 4), (2024, 7), (2024, 10), (2025, 1), (2025, 4), (2025, 7), (2025, 10)]:
        s_ = ts(Y, M); e_ = min(s_ + 365 * 86400.0, ts(2026, 10))
        out.append(f"{Y % 100}.{M:02d}: ${sim2(t0, t1, R, STv, STH, int(np.searchsorted(t0, s_)), e_, 20, 0.04, -0.025)[0]:,.0f}")
    print(f"{nm:30s} " + " · ".join(out), flush=True)
r_t = money2("стоп касанием 2, тейк 1.1", pool(E, mk3(1.1, 2.0, 2.0)), 2.0)
for hard in (2.5, 2.75):
    money2(f"закр. свечи графика, авар. {hard}", pool(E, mk2(2.0, hard, lambda e: e["tfh"])), hard, ref=r_t)
money2("закр. свечи графика, авар. 3", pool(E, mk2(2.0, 3.0, lambda e: e["tfh"])), 3.0, ref=r_t)
print("== год со старта квартала ($100 -> ; 25.10 = последние 12 мес)")
by_q("стоп касанием 2, тейк 1.1", pool(E, mk3(1.1, 2.0, 2.0)), 2.0)
by_q("закр. 1ч, авар. 3 (692)", pool(E, mk2(2.0, 3.0, lambda e: 1)), 3.0)
by_q("закр. свечи графика, авар. 3", pool(E, mk2(2.0, 3.0, lambda e: e["tfh"])), 3.0)
by_q("закр. свечи графика, авар. 2.75", pool(E, mk2(2.0, 2.75, lambda e: e["tfh"])), 2.75)
