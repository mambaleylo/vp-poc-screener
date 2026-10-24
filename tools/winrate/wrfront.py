"""the user wants a high win rate: the honest frontier of win rate vs money. Exits walked on the 1h candles from the touch
hour (the stop first in an hour, no take in the touch hour): take k ATR (no extension) or the v0.99.690 take (2 ATR, 1
after a 0.4 dip); stop by a touch of s ATR, or at a 1h close beyond s with an emergency stop h (sized by s); the model's
threshold top 1% / 0.5%; 4h alone / 4h + 2h; the pool in the honest order, money at 20 positions x 4%"""
exec(open("tournament.py").read().split("S = {")[0])
@njit
def walk3(T, O, H, L, C, i1, end_t, s, fill, a, tk, far, n, soft, hard, close_mode):
    risk = soft * a; hsl = fill - s * hard * a; ssl = fill - s * soft * a
    tp1 = fill + s * tk * a; tp2 = fill + s * far * a; mae = 0.0; ext = False; pulled = False
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
                    return (s * (tp2 - fill) - (0.0004 + 0.0003 * (q + 1) / 24) * fill) / risk, 1, T[b] + 3600
            elif (s > 0 and H[b] >= tp1) or (s < 0 and L[b] <= tp1):
                if n > 0 and not pulled and max(mae, adv) < n * a:
                    ext = True
                else:
                    return (s * (tp1 - fill) - (0.0004 + 0.0003 * (q + 1) / 24) * fill) / risk, 1, T[b] + 3600
        if close_mode and ((s > 0 and C[b] <= ssl) or (s < 0 and C[b] >= ssl)):
            return (s * (C[b] - fill) - (0.0007 + 0.0003 * (q + 1) / 24) * fill) / risk, 0, T[b] + 3600
        if adv > mae: mae = adv
        if not ext and n > 0 and mae >= n * a: pulled = True
        b += 1
    b = min(b, len(C)) - 1
    return (s * (C[b] - fill) - (0.0007 + 0.0003 * (b - i1 + 1) / 24) * fill) / risk, 3, T[b] + 3600
H1C = {}
def h1c(sym):
    if sym not in H1C:
        T, O, H, L, C, V = E1.load15(sym); H1C[sym] = (T.astype(np.int64), O, H, L, C)
    return H1C[sym]
def events2(dr, fi, scf, eng, tfh, anchor, depth, q):
    os.environ["TFH"] = str(tfh); E = importlib.import_module(eng)
    X = merged(dr, fi); z = np.load(scf, allow_pickle=True); SC, THR = z["SC"], z["THR"].item(); T = X["t"]
    yr = T.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970; thr = np.full(len(T), np.inf)
    for Y, v in THR.items(): thr[yr == Y] = np.quantile(v, q)
    out, cache = [], {}
    for i in np.flatnonzero(~X["usdc"] & np.isfinite(SC) & (SC >= thr) & (T >= ts(2022))):
        sym = X["names"][X["sym"][i]]; s = int(X["side"][i]); t = int(T[i])
        if sym not in cache:
            Tb, O, H, L, C, V = E.load15(sym); cache[sym] = (Tb, O, H, L, C, E.wilder(H, L, C, 14), {int(x): j for j, x in enumerate(Tb)})
        Tb, O, H, L, C, atr, pos = cache[sym]; bi = pos[t]; a = float(atr[bi])
        lv = ((L[bi] if s > 0 else H[bi]) if anchor == "wick" else C[bi]) - s * depth * a
        fb = next((b for b in range(bi + 1, bi + 5) if ((L[b] <= lv) if s > 0 else (H[b] >= lv))), -1)
        if fb < 0: continue
        fill = min(lv, O[fb]) if s > 0 else max(lv, O[fb])
        T1, O1, H1_, L1, C1 = h1c(sym); j0, j1 = int(np.searchsorted(T1, Tb[fb])), int(np.searchsorted(T1, Tb[fb] + tfh * 3600))
        i1 = -1
        for b in range(j0, j1):
            if (L1[b] <= lv) if s > 0 else (H1_[b] >= lv): i1 = b; break
        if i1 < 0: continue
        out.append(dict(key=(int(T1[i1]), s * (O1[i1] - lv) / a, -float(SC[i]), t), sym=sym, s=s, lv=lv, fill=fill, a=a, i1=i1, end_t=int(Tb[fb]) + 32 * tfh * 3600))
    return out
EVQ = {}
for q in (0.99, 0.995):
    EVQ[q] = {"4h": events2("s23_4h", 2, "s26_s23_4h_w1_0.npz", "s23_engine", 4, "wick", 1.0, q),
              "2h": events2("s21h2", 0, "s26_s21h2_d2_1.npz", "s21h2_engine", 2, "close", 2.0, q)}
    print("loaded q", q, {k: len(v) for k, v in EVQ[q].items()}, flush=True)
roll = np.arange(ts(2024), ts(2025, 10) + 1, 7 * 86400.0)
def show(nm, evs, tk, far, n, soft, hard, cm):
    rows = []
    for e in evs:
        T, O, H, L, C = h1c(e["sym"])
        R, k, te = walk3(T, O, H, L, C, e["i1"], e["end_t"], e["s"], e["fill"], e["a"], tk, far, n, soft, hard, cm)
        rows.append((e["key"], e["sym"], e["s"], int(te), float(R), float(np.clip(soft * e["a"] / e["fill"], 0.002, 0.5)), int(k)))
    rows.sort(key=lambda x: x[0]); busy, act, P = {}, [], []
    for key, sym, s, end, R, st, k in rows:
        ft = key[0]
        if busy.get((sym, s), 0) > ft: continue
        act = [x for x in act if x[0] > ft]
        if sum(1 for x in act if x[1] == s) >= 20: continue
        busy[(sym, s)] = end; act.append((end, s)); P.append((ft, end, R, st, k))
    P = np.array(sorted(P), float); t0, t1, R, STv, K = P.T
    y = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.025) for s_ in roll])
    l12 = sim(t0, t1, R, STv, int(np.searchsorted(t0, ts(2025, 10))), ts(2026, 10), 20, 0.04, -0.025)
    wr = np.mean(K == 1) * 100; wr_pos = np.mean(R > 0) * 100
    print(f"{nm:52s} n{len(R):5d} WR {wr:3.0f}% (в плюс {wr_pos:3.0f}%) {R.mean():+.3f}R | медиана ${np.median(y[:, 0]):>7,.0f} 10% ${np.percentile(y[:, 0], 10):>6,.0f} "
          f"просадка {np.median(y[:, 1])*100:.0f}% | с 10.2025 ${l12[0]:,.0f}", flush=True)
for q in (0.99, 0.995):
    for streams in (("4h",), ("4h", "2h")):
        evs = sum((EVQ[q][x] for x in streams), [])
        lab = f"{'1%' if q == 0.99 else '0.5%'} {'4ч' if len(streams) == 1 else '4ч+2ч'}"
        show(f"{lab}: тейк 2/1 ATR, стоп 2 (сейчас)", evs, 1.0, 2.0, 0.4, 2.0, 2.0, False)
        for tk in (1.0, 0.75, 0.5):
            show(f"{lab}: тейк {tk}, стоп 2", evs, tk, 0, 0, 2.0, 2.0, False)
        for tk, st in ((1.0, 3.0), (0.75, 3.0), (0.5, 3.0), (0.75, 2.5)):
            show(f"{lab}: тейк {tk}, стоп {st}", evs, tk, 0, 0, st, st, False)
        for tk in (1.0, 0.75):
            show(f"{lab}: тейк {tk}, стоп закр.часа 2 / авар. 3", evs, tk, 0, 0, 2.0, 3.0, True)
