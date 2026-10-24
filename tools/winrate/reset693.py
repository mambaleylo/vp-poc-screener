"""the user: "куча стопов ложных, после разворота после касания стопа основного и если потом цена дошла до точки входа
сбрасывать таймер свечей для закрытия по времени" — the v0.99.692 exits (take 1.1, a 1h close beyond 2 ATR, the emergency
3), plus: once a wick reached the stop level (dep ATR against) and the price then came back to the entry (back ATR from it),
the hold timer restarts from that hour (max_r restarts). The 4h + 2h pool in the honest order, 1h walk"""
exec(open("sweep692.py").read().split("EVQ = {}")[0].replace("def show(nm, evs, hold=32, alive=4, cap=20, rk=0.04):", "def show_old(nm, evs, hold=32, alive=4, cap=20, rk=0.04):"))
@njit
def walk4(T, O, H, L, C, i1, end_t, hold_sec, s, fill, a, tk, soft, hard, dep, back, max_r):
    risk = soft * a; hsl = fill - s * hard * a; ssl = fill - s * soft * a; tp1 = fill + s * tk * a
    dl = fill - s * dep * a; bk = fill - s * back * a; deep = False; nr = 0
    b = i1
    while b < len(C) and T[b] < end_t:
        q = b - i1
        if (s > 0 and L[b] <= hsl) or (s < 0 and H[b] >= hsl):
            x = O[b] if (q > 0 and ((s > 0 and O[b] <= hsl) or (s < 0 and O[b] >= hsl))) else hsl
            return (s * (x - fill) - (0.0007 + 0.0003 * (q + 1) / 24) * fill) / risk, 0, T[b] + 3600, nr
        if q > 0 and ((s > 0 and H[b] >= tp1) or (s < 0 and L[b] <= tp1)):
            return (s * (tp1 - fill) - (0.0004 + 0.0003 * (q + 1) / 24) * fill) / risk, 1, T[b] + 3600, nr
        if (s > 0 and C[b] <= ssl) or (s < 0 and C[b] >= ssl):
            return (s * (C[b] - fill) - (0.0007 + 0.0003 * (q + 1) / 24) * fill) / risk, 0, T[b] + 3600, nr
        if deep and nr < max_r and ((s > 0 and H[b] >= bk) or (s < 0 and L[b] <= bk)):
            end_t = T[b] + 3600 + hold_sec; nr += 1; deep = False
        if (s > 0 and L[b] <= dl) or (s < 0 and H[b] >= dl):
            deep = True
        b += 1
    b = min(b, len(C)) - 1
    return (s * (C[b] - fill) - (0.0007 + 0.0003 * (b - i1 + 1) / 24) * fill) / risk, 3, T[b] + 3600, nr
def show(nm, evs, hold=32, cap=20, rk=0.04, dep=2.0, back=0.0, max_r=0):
    rows = []; nres = 0
    for e in evs:
        if e["nb"] > 4: continue
        T, O, H, L, C = h1c(e["sym"]); hs = hold * e["tfh"] * 3600
        R, k, te, nr = walk4(T, O, H, L, C, e["i1"], e["fbt"] + hs, hs, e["s"], e["fill"], e["a"], 1.1, 2.0, 3.0, dep, back, max_r)
        rows.append((e["key"], e["sym"], e["s"], int(te), float(R), float(np.clip(2 * e["a"] / e["fill"], 0.002, 0.5)), int(k), int(nr)))
    rows.sort(key=lambda x: x[0]); busy, act, P = {}, [], []
    for key, sym, s, end, R, st, k, nr in rows:
        ft = key[0]
        if busy.get((sym, s), 0) > ft: continue
        act = [x for x in act if x[0] > ft]
        if sum(1 for x in act if x[1] == s) >= cap: continue
        busy[(sym, s)] = end; act.append((end, s)); P.append((ft, end, R, st, k, nr))
    P = np.array(sorted(P), float); t0, t1, R, STv, K, NR = P.T
    y = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, rk, -0.025) for s_ in roll])
    yh = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, rk, -0.04)[0] for s_ in roll])
    l12 = sim(t0, t1, R, STv, int(np.searchsorted(t0, ts(2025, 10))), ts(2026, 10), 20, rk, -0.025)
    yrs = (t0.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970)
    ys = " ".join(f"{Y % 100}:{R[yrs == Y].mean():+.2f}" for Y in range(2022, 2027))
    print(f"{nm:36s} n{len(R):5d} WR {np.mean(K == 1)*100:.0f}% {R.mean():+.3f}R врем {np.mean(K == 3)*100:.0f}% сброс {int((NR > 0).sum())} | медиана ${np.median(y[:, 0]):>6,.0f} 10% ${np.percentile(y[:, 0], 10):>5,.0f} "
          f"просадка {np.median(y[:, 1])*100:.0f}% жёстко ${np.median(yh):,.0f} | с 10.2025 ${l12[0]:,.0f} | {ys}", flush=True)
E = events3("s23_4h", 2, "s26_s23_4h_w1_0.npz", "s23_engine", 4, "wick", 1.0, 0.99) + events3("s21h2", 0, "s26_s21h2_d2_1.npz", "s21h2_engine", 2, "close", 2.0, 0.99)
show("сейчас (692)", E)
print("== касание стопа тенью (2 ATR), потом цена у входа -> таймер заново")
for mr in (1, 2, 99): show(f"сброс до {mr if mr < 99 else 'без лимита'} раз", E, back=0.0, max_r=mr)
print("== глубина касания / насколько вернуться к входу (1 раз)")
for dep in (1.5, 1.75): show(f"касание {dep} ATR, возврат к входу", E, dep=dep, max_r=1)
for bk in (0.25, 0.5): show(f"касание 2 ATR, возврат до -{bk} ATR", E, back=bk, max_r=1)
print("== для сравнения: просто держать дольше")
for h in (48, 64): show(f"держать {h} (без сброса)", E, hold=h)
