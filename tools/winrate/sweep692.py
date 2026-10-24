"""the settings around the v0.99.692 exits (they had been tuned for the old ones): the hold (bars of the chart), the order's
life (bars), the model's threshold, the side's cap, the risk — the 4h + 2h pool in the honest order, 1h walk"""
exec(open("wrfront.py").read().split("def events2")[0])
def events3(dr, fi, scf, eng, tfh, anchor, depth, q, alive=6):
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
        fb = next((b for b in range(bi + 1, min(len(C), bi + 1 + alive)) if ((L[b] <= lv) if s > 0 else (H[b] >= lv))), -1)
        if fb < 0: continue
        fill = min(lv, O[fb]) if s > 0 else max(lv, O[fb])
        T1, O1, H1_, L1, C1 = h1c(sym); j0, j1 = int(np.searchsorted(T1, Tb[fb])), int(np.searchsorted(T1, Tb[fb] + tfh * 3600))
        i1 = next((b for b in range(j0, j1) if ((L1[b] <= lv) if s > 0 else (H1_[b] >= lv))), -1)
        if i1 < 0: continue
        out.append(dict(key=(int(T1[i1]), s * (O1[i1] - lv) / a, -float(SC[i]), t), sym=sym, s=s, fill=fill, a=a, i1=i1, fbt=int(Tb[fb]), nb=fb - bi, tfh=tfh))
    return out
roll = np.arange(ts(2024), ts(2025, 10) + 1, 7 * 86400.0)
def show(nm, evs, hold=32, alive=4, cap=20, rk=0.04):
    rows = []
    for e in evs:
        if e["nb"] > alive: continue
        T, O, H, L, C = h1c(e["sym"])
        R, k, te = walk3(T, O, H, L, C, e["i1"], e["fbt"] + hold * e["tfh"] * 3600, e["s"], e["fill"], e["a"], 1.1, 0, 0, 2.0, 3.0, True)
        rows.append((e["key"], e["sym"], e["s"], int(te), float(R), float(np.clip(2 * e["a"] / e["fill"], 0.002, 0.5)), int(k)))
    rows.sort(key=lambda x: x[0]); busy, act, P = {}, [], []
    for key, sym, s, end, R, st, k in rows:
        ft = key[0]
        if busy.get((sym, s), 0) > ft: continue
        act = [x for x in act if x[0] > ft]
        if sum(1 for x in act if x[1] == s) >= cap: continue
        busy[(sym, s)] = end; act.append((end, s)); P.append((ft, end, R, st, k))
    P = np.array(sorted(P), float); t0, t1, R, STv, K = P.T
    y = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, rk, -0.025) for s_ in roll])
    yh = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, rk, -0.04)[0] for s_ in roll])
    l12 = sim(t0, t1, R, STv, int(np.searchsorted(t0, ts(2025, 10))), ts(2026, 10), 20, rk, -0.025)
    print(f"{nm:34s} n{len(R):5d} WR {np.mean(K == 1)*100:.0f}% {R.mean():+.3f}R | медиана ${np.median(y[:, 0]):>7,.0f} 10% ${np.percentile(y[:, 0], 10):>6,.0f} "
          f"просадка {np.median(y[:, 1])*100:.0f}% жёстко ${np.median(yh):,.0f} | с 10.2025 ${l12[0]:,.0f}", flush=True)
EVQ = {}
for q in (0.985, 0.99, 0.993):
    EVQ[q] = events3("s23_4h", 2, "s26_s23_4h_w1_0.npz", "s23_engine", 4, "wick", 1.0, q) + events3("s21h2", 0, "s26_s21h2_d2_1.npz", "s21h2_engine", 2, "close", 2.0, q)
    print("loaded", q, len(EVQ[q]), flush=True)
E = EVQ[0.99]
show("сейчас (692)", E)
print("== удержание (свечей графика)")
for h in (16, 24, 48, 64): show(f"держать {h}", E, hold=h)
print("== жизнь лимитки (свечей)")
for a_ in (2, 3, 5, 6): show(f"лимитка живёт {a_}", E, alive=a_)
print("== порог модели")
show("лучшие 1.5%", EVQ[0.985]); show("лучшие 0.7%", EVQ[0.993])
print("== лимит в сторону / риск")
for c in (12, 15, 25, 30): show(f"в сторону {c}", E, cap=c)
for r in (0.03, 0.05, 0.06): show(f"риск {r*100:.0f}%", E, rk=r)
