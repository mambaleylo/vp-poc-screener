"""the audit: the pool's order of fills at the 1h resolution. The research pool ordered the fills by their bar's open — a
4h order's fill got its 4h bar's open, up to 4h before the real touch, so at a busy coin / a full side the 4h orders won
over the 2h ones. Here the touch time = the first 1h bar inside the fill bar reaching the level (ties: the score);
the trades and the money with the v0.99.690 exit, vs the bar-open order"""
exec(open("tkext.py").read().split("\nroll = np.arange")[0])
import s19h_engine as E1
H1 = {}
def touch1h(sym, ft, bs, s, lv):
    if sym not in H1:
        T, O, H, L, C, V = E1.load15(sym); H1[sym] = (T, H, L)
    T, H, L = H1[sym]; i = int(np.searchsorted(T, ft)); j = int(np.searchsorted(T, ft + bs))
    for b in range(i, j):
        if (L[b] <= lv) if s > 0 else (H[b] >= lv): return int(T[b])
    return ft   # the 1h data missing a bar: the bar's open
for v in EV:
    v["ft1"] = touch1h(v["sym"], v["ft"], v["tfh"] * 3600, v["s"], v["lv"])
print("4h fills: the touch later than the bar's open by", np.mean([v["ft1"] - v["ft"] for v in EV if v["tfh"] == 4]) / 3600, "h on average", flush=True)
def run1(n, e, key):
    rows = []
    for v in EV:
        Tb, O, H, L, C, atr, pos = BARS[(v["sym"], v["tfh"])]
        R, k, kk = ex(O, H, L, C, v["fb"], v["s"], v["fill"], v["a"], n, e, 0, v["tfh"])
        rows.append((v[key], v["nsc"], v["t"], v["sym"], v["s"], int(Tb[v["fb"] + kk]) + v["tfh"] * 3600, R, float(np.clip(2 * v["a"] / v["fill"], 0.002, 0.5)), k))
    rows.sort(key=lambda x: (x[0], x[1], x[2])); busy, act, P = {}, [], []
    for ft, nsc, t, sym, s, end, R, st, k in rows:
        if busy.get((sym, s), 0) > ft: continue
        act = [x for x in act if x[0] > ft]
        if sum(1 for x in act if x[1] == s) >= 20: continue
        busy[(sym, s)] = end; act.append((end, s)); P.append((ft, end, R, st, k))
    P.sort(key=lambda x: x[0]); return np.array(P, float)
roll = np.arange(ts(2024), ts(2025, 10) + 1, 7 * 86400.0)
for nm, key in (("по открытию свечи (как сейчас)", "ft"), ("по часовой свече касания", "ft1")):
    P = run1(0.4, 1.0, key); t0, t1, R, STv = P[:, 0], P[:, 1], P[:, 2], P[:, 3]
    y = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.025) for s_ in roll])
    yh = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.04)[0] for s_ in roll])
    l12 = sim(t0, t1, R, STv, int(np.searchsorted(t0, ts(2025, 10))), ts(2026, 10), 20, 0.04, -0.025)
    yr = (t0 // 31557600 + 1970).astype(int)
    print(f"{nm:32s} n{len(R)} {R.mean():+.3f}R [{' '.join(f'{y_ % 100}:{R[yr == y_].mean():+.2f}' for y_ in range(2022, 2027))}] | медиана ${np.median(y[:, 0]):,.0f} "
          f"10% ${np.percentile(y[:, 0], 10):,.0f} просадка {np.median(y[:, 1])*100:.0f}% | жёстко ${np.median(yh):,.0f} | с 10.2025 ${l12[0]:,.0f}", flush=True)
