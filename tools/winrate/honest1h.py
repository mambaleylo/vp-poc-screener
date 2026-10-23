"""the audit: the decisions of v0.99.689 (+ the 2h stream) and v0.99.690 (the take) again with the fills ordered by the
1h bar of the touch (pool1h.py) — 4h alone / 4h + 2h, the take 1 ATR / 2 ATR unless a dip of n; the side cap"""
exec(open("pool1h.py").read().split('print("4h fills')[0])
EV_ALL = EV
roll = np.arange(ts(2024), ts(2025, 10) + 1, 7 * 86400.0)
def run2(evs, n, e, cap=20):
    rows = []
    for v in evs:
        Tb, O, H, L, C, atr, pos = BARS[(v["sym"], v["tfh"])]
        R, k, kk = ex(O, H, L, C, v["fb"], v["s"], v["fill"], v["a"], n, e, 0, v["tfh"])
        rows.append((v["ft1"], v["nsc"], v["t"], v["sym"], v["s"], int(Tb[v["fb"] + kk]) + v["tfh"] * 3600, R, float(np.clip(2 * v["a"] / v["fill"], 0.002, 0.5)), k))
    rows.sort(key=lambda x: (x[0], x[1], x[2])); busy, act, P = {}, [], []
    for ft, nsc, t, sym, s, end, R, st, k in rows:
        if busy.get((sym, s), 0) > ft: continue
        act = [x for x in act if x[0] > ft]
        if sum(1 for x in act if x[1] == s) >= cap: continue
        busy[(sym, s)] = end; act.append((end, s)); P.append((ft, end, R, st, k))
    P.sort(key=lambda x: x[0]); return np.array(P, float)
def show(nm, evs, n, e, cap=20, mp=20):
    P = run2(evs, n, e, cap); t0, t1, R, STv, K = P[:, 0], P[:, 1], P[:, 2], P[:, 3], P[:, 4]
    y = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, mp, 0.04, -0.025) for s_ in roll])
    yh = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, mp, 0.04, -0.04)[0] for s_ in roll])
    fx = []
    for st in ((2024, 1), (2024, 7), (2025, 1), (2025, 4), (2025, 7), (2025, 10)):
        s_ = ts(*st); v = sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0 if st < (2025, 10) else ts(2026, 10), mp, 0.04, -0.025)
        fx.append(f"{st[0] % 100}.{st[1]:02d}→${v[0]:,.0f}")
    yr = (t0 // 31557600 + 1970).astype(int)
    print(f"{nm:36s} n{len(R)} {R.mean():+.3f}R WR {np.isin(K, (1, 2)).mean()*100:.0f}% [{' '.join(f'{y_ % 100}:{R[yr == y_].mean():+.2f}' for y_ in range(2023, 2027))}] | медиана ${np.median(y[:, 0]):,.0f} "
          f"10% ${np.percentile(y[:, 0], 10):,.0f} просадка {np.median(y[:, 1])*100:.0f}% | жёстко ${np.median(yh):,.0f} | " + " ".join(fx), flush=True)
W4 = [v for v in EV_ALL if v["tfh"] == 4]
show("4ч одна, тейк 1 ATR (v0.99.688)", W4, 0, 0)
show("4ч одна, новый тейк", W4, 0.4, 1.0)
show("4ч + 2ч, тейк 1 ATR (v0.99.689)", EV_ALL, 0, 0)
show("4ч + 2ч, новый тейк (v0.99.690)", EV_ALL, 0.4, 1.0)
for n in (0.3, 0.5): show(f"4ч + 2ч, откат {n}", EV_ALL, n, 1.0)
show("4ч одна, откат 0.5", W4, 0.5, 1.0)
for cap, mp in ((30, 20), (40, 20), (30, 30), (999, 20)):
    show(f"4ч + 2ч, новый тейк, {cap} в сторону, {mp} позиций", EV_ALL, 0.4, 1.0, cap, mp)
