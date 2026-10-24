"""follow-up of the user's "куча стопов ложных": (1) the 692 close-stops — how many would have reached the take later
(within the hold) without being stopped; (2) the stop checked on the close of a longer candle (2h / 4h) instead of 1h,
the stop distance 2 / 2.5 ATR with the emergency 3 / 3.5 ATR. The 4h + 2h pool in the honest order"""
exec(open("reset693.py").read().split("E = events3(")[0])
@njit
def walk5(T, O, H, L, C, i1, end_t, s, fill, a, tk, soft, hard, kh, size_by):
    risk = size_by * a; hsl = fill - s * hard * a; ssl = fill - s * soft * a; tp1 = fill + s * tk * a
    b = i1
    while b < len(C) and T[b] < end_t:
        q = b - i1
        if (s > 0 and L[b] <= hsl) or (s < 0 and H[b] >= hsl):
            x = O[b] if (q > 0 and ((s > 0 and O[b] <= hsl) or (s < 0 and O[b] >= hsl))) else hsl
            return (s * (x - fill) - (0.0007 + 0.0003 * (q + 1) / 24) * fill) / risk, 0, T[b] + 3600
        if q > 0 and ((s > 0 and H[b] >= tp1) or (s < 0 and L[b] <= tp1)):
            return (s * (tp1 - fill) - (0.0004 + 0.0003 * (q + 1) / 24) * fill) / risk, 1, T[b] + 3600
        if (T[b] + 3600) % (kh * 3600) == 0 and ((s > 0 and C[b] <= ssl) or (s < 0 and C[b] >= ssl)):
            return (s * (C[b] - fill) - (0.0007 + 0.0003 * (q + 1) / 24) * fill) / risk, 4, T[b] + 3600
        b += 1
    b = min(b, len(C)) - 1
    return (s * (C[b] - fill) - (0.0007 + 0.0003 * (b - i1 + 1) / 24) * fill) / risk, 3, T[b] + 3600
def pool(evs, f):
    rows = []
    for e in evs:
        if e["nb"] > 4: continue
        R, k, te = f(e)
        rows.append((e["key"], e["sym"], e["s"], int(te), float(R), float(np.clip(2 * e["a"] / e["fill"], 0.002, 0.5)), int(k), e))
    rows.sort(key=lambda x: x[0]); busy, act, P = {}, [], []
    for key, sym, s, end, R, st, k, e in rows:
        ft = key[0]
        if busy.get((sym, s), 0) > ft: continue
        act = [x for x in act if x[0] > ft]
        if sum(1 for x in act if x[1] == s) >= 20: continue
        busy[(sym, s)] = end; act.append((end, s)); P.append((ft, end, R, st, k, e))
    return sorted(P, key=lambda x: x[:5])
def money(nm, P, rk=0.04):
    A = np.array([p[:5] for p in P], float); t0, t1, R, STv, K = A.T
    y = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, rk, -0.025) for s_ in roll])
    yh = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, rk, -0.04)[0] for s_ in roll])
    l12 = sim(t0, t1, R, STv, int(np.searchsorted(t0, ts(2025, 10))), ts(2026, 10), 20, rk, -0.025)
    yrs = (t0.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970)
    ys = " ".join(f"{Y % 100}:{R[yrs == Y].mean():+.2f}" for Y in range(2022, 2027))
    print(f"{nm:34s} n{len(R):5d} WR {np.mean(K == 1)*100:.0f}% {R.mean():+.3f}R стоп-закр {np.mean(K == 4)*100:.0f}% авар {np.mean(K == 0)*100:.1f}% | медиана ${np.median(y[:, 0]):>6,.0f} 10% ${np.percentile(y[:, 0], 10):>5,.0f} "
          f"просадка {np.median(y[:, 1])*100:.0f}% жёстко ${np.median(yh):,.0f} | с 10.2025 ${l12[0]:,.0f} | {ys}", flush=True)
E = events3("s23_4h", 2, "s26_s23_4h_w1_0.npz", "s23_engine", 4, "wick", 1.0, 0.99) + events3("s21h2", 0, "s26_s21h2_d2_1.npz", "s21h2_engine", 2, "close", 2.0, 0.99)
def mk(soft, hard, kh, size_by=2.0):
    def f(e):
        T, O, H, L, C = h1c(e["sym"])
        return walk5(T, O, H, L, C, e["i1"], e["fbt"] + 32 * e["tfh"] * 3600, e["s"], e["fill"], e["a"], 1.1, soft, hard, kh, size_by)
    return f
P0 = pool(E, mk(2.0, 3.0, 1)); money("сейчас: закр. 1ч за 2, авар. 3", P0)
# (1) the close-stops of the deployed rule: later reached the take (no stop at all, only the emergency 3 ATR / the hold)?
st = [p for p in P0 if p[4] == 4]; later = 0; later_dd = 0
for p in st:
    e = p[5]; T, O, H, L, C = h1c(e["sym"])
    R2, k2, _ = walk5(T, O, H, L, C, e["i1"], e["fbt"] + 32 * e["tfh"] * 3600, e["s"], e["fill"], e["a"], 1.1, 99.0, 3.0, 1, 2.0)
    later += k2 == 1
print(f"стопов по закрытию часа: {len(st)}; из них без этого стопа дошли бы до тейка (до авар. 3 ATR и конца срока): {later} ({later / len(st) * 100:.0f}%)")
print("== стоп по закрытию свечи подлиннее / дальше")
money("закр. 2ч за 2, авар. 3", pool(E, mk(2.0, 3.0, 2)))
money("закр. 4ч за 2, авар. 3", pool(E, mk(2.0, 3.0, 4)))
money("закр. 1ч за 2.5, авар. 3.5", pool(E, mk(2.5, 3.5, 1, 2.5)))
money("закр. 4ч за 2.5, авар. 3.5", pool(E, mk(2.5, 3.5, 4, 2.5)))
money("без стопа по закрытию, авар. 3", pool(E, mk(99.0, 3.0, 1, 3.0)))
