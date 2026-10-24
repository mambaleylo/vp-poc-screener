"""the user (a GRASS 2h trade stopped by a wick, then the take): protection from wick stops, with the v0.99.690 take
(2 ATR, back to 1 ATR after a 0.4 ATR dip) and the honest pool order (the touch's 1h bar, the nearer level first).
The trades walked on the 1h candles from the touch hour (the stop first in an hour, no take in the touch hour):
  touch k   — the stop when the price touches k ATR (k = 2 deployed);
  close a/h — out at the 1h close beyond a ATR; an emergency stop on a touch of h ATR; the position sized by the
              emergency stop ("размер от аварийного") or by a ("размер от a": the emergency then costs -h/a R).
The pool, 20 a side, money at 20 positions x 4% (the leverage by the sizing stop), cautious / harsh."""
exec(open("tkext.py").read().split("\nroll = np.arange")[0])
import s19h_engine as E1
H1 = {}
def h1(sym):
    if sym not in H1:
        T, O, H, L, C, V = E1.load15(sym); H1[sym] = (T.astype(np.int64), O, H, L, C)
    return H1[sym]
for v in EV:
    T, O, H, L, C = h1(v["sym"]); bs = v["tfh"] * 3600; i, j = int(np.searchsorted(T, v["ft"])), int(np.searchsorted(T, v["ft"] + bs))
    v["i1"] = -1
    for b in range(i, j):
        if (L[b] <= v["lv"]) if v["s"] > 0 else (H[b] >= v["lv"]): v["i1"] = b; v["d1"] = v["s"] * (O[b] - v["lv"]) / v["a"]; break
    v["end_t"] = v["ft"] + 32 * bs   # the hold: 32 bars of the chart from the fill bar
EV = [v for v in EV if v["i1"] >= 0]
@njit
def walk(T, O, H, L, C, i1, end_t, s, fill, a, soft, hard, close_mode, size_by, n, far):
    """-> (R per the sizing stop, kind: 0 stop / 1 take / 2 far take / 3 time / 4 close-stop, exit time)"""
    risk = size_by * a; hsl = fill - s * hard * a; ssl = fill - s * soft * a
    tp1 = fill + s * a; tp2 = fill + s * far * a; mae = 0.0; ext = False; pulled = False
    b = i1
    while b < len(C) and T[b] < end_t:
        q = b - i1
        adv = (fill - L[b]) if s > 0 else (H[b] - fill)
        if (s > 0 and L[b] <= hsl) or (s < 0 and H[b] >= hsl):
            x = O[b] if (q > 0 and ((s > 0 and O[b] <= hsl) or (s < 0 and O[b] >= hsl))) else hsl
            return (s * (x - fill) - (0.0007 + 0.0003 * (q + 1) / 24) * fill) / risk, 0, T[b] + 3600
        if q > 0:
            if ext:
                if (s > 0 and H[b] >= tp2) or (s < 0 and L[b] <= tp2):
                    return (s * (tp2 - fill) - (0.0004 + 0.0003 * (q + 1) / 24) * fill) / risk, 2, T[b] + 3600
            elif pulled:
                if (s > 0 and H[b] >= tp1) or (s < 0 and L[b] <= tp1):
                    return (s * (tp1 - fill) - (0.0004 + 0.0003 * (q + 1) / 24) * fill) / risk, 1, T[b] + 3600
            elif (s > 0 and H[b] >= tp1) or (s < 0 and L[b] <= tp1):
                if n > 0 and max(mae, adv) < n * a:
                    ext = True
                else:
                    return (s * (tp1 - fill) - (0.0004 + 0.0003 * (q + 1) / 24) * fill) / risk, 1, T[b] + 3600
        if close_mode and ((s > 0 and C[b] <= ssl) or (s < 0 and C[b] >= ssl)):
            return (s * (C[b] - fill) - (0.0007 + 0.0003 * (q + 1) / 24) * fill) / risk, 4, T[b] + 3600
        if adv > mae: mae = adv
        if not ext and mae >= n * a: pulled = True
        b += 1
    b = min(b, len(C)) - 1
    return (s * (C[b] - fill) - (0.0007 + 0.0003 * (b - i1 + 1) / 24) * fill) / risk, 3, T[b] + 3600
roll = np.arange(ts(2024), ts(2025, 10) + 1, 7 * 86400.0)
def show(nm, soft, hard, close_mode, size_by):
    rows = []
    for v in EV:
        T, O, H, L, C = h1(v["sym"])
        R, k, te = walk(T, O, H, L, C, v["i1"], v["end_t"], v["s"], v["fill"], v["a"], soft, hard, close_mode, size_by, 0.4, 2.0)
        rows.append(((int(T[v["i1"]]), v["d1"]), v["nsc"], v["t"], v["sym"], v["s"], int(te), float(R), float(np.clip(size_by * v["a"] / v["fill"], 0.002, 0.5)), int(k)))
    rows.sort(key=lambda x: (x[0], x[1], x[2])); busy, act, P = {}, [], []
    for (ft, _d), nsc, t, sym, s, end, R, st, k in rows:
        if busy.get((sym, s), 0) > ft: continue
        act = [x for x in act if x[0] > ft]
        if sum(1 for x in act if x[1] == s) >= 20: continue
        busy[(sym, s)] = end; act.append((end, s)); P.append((ft, end, R, st, k))
    P = np.array(sorted(P), float); t0, t1, R, STv, K = P.T
    y = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.025) for s_ in roll])
    yh = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.04)[0] for s_ in roll])
    l12 = sim(t0, t1, R, STv, int(np.searchsorted(t0, ts(2025, 10))), ts(2026, 10), 20, 0.04, -0.025)
    print(f"{nm:44s} n{len(R)} {R.mean():+.3f}R WR {np.isin(K, (1, 2)).mean()*100:.0f}% стопов {np.isin(K, (0, 4)).mean()*100:.0f}% (аварийных {np.mean(K == 0)*100:.0f}%) | "
          f"медиана ${np.median(y[:, 0]):,.0f} 10% ${np.percentile(y[:, 0], 10):,.0f} просадка {np.median(y[:, 1])*100:.0f}% | жёстко ${np.median(yh):,.0f} | с 10.2025 ${l12[0]:,.0f}", flush=True)
show("касанием 2 ATR (сейчас, по часовым)", 2.0, 2.0, False, 2.0)
show("касанием 2.5 ATR", 2.5, 2.5, False, 2.5)
show("касанием 3 ATR", 3.0, 3.0, False, 3.0)
for soft, hard in ((2.0, 3.0), (2.0, 4.0), (1.5, 3.0), (2.5, 3.5)):
    show(f"закрытие часа {soft} / аварийный {hard}, размер от аварийного", soft, hard, True, hard)
    show(f"закрытие часа {soft} / аварийный {hard}, размер от {soft}", soft, hard, True, soft)
