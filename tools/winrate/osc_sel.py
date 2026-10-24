"""⚡ selection by the daily WaveTrend: the model's threshold lower when the daily oscillator is stretched against the trade
(wt1 x side <= -3), higher when with it (>= 22). The candidates at q 0.98+ with their score's percentile (vs the previous
year's out-of-sample scores, as the deployed threshold), the same exits / pool / money as v0.99.704"""
src = open("dynrisk4.py").read().split("for nm, lv, rk in")[0]
exec(src)
import gh_lib as GH
def events_q(dr, fi, scf, eng, tfh, anchor, depth, qlo, alive=6):
    os.environ["TFH"] = str(tfh); Em = importlib.import_module(eng)
    X = merged(dr, fi); z = np.load(scf, allow_pickle=True); SC, THR = z["SC"], z["THR"].item(); T = X["t"]
    yr = T.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970
    thr = np.full(len(T), np.inf); pq = np.full(len(T), np.nan)
    for Y, v in THR.items():
        m = yr == Y; thr[m] = np.quantile(v, qlo); sv = np.sort(v); pq[m] = np.searchsorted(sv, SC[m]) / len(sv)
    out, cache = [], {}
    for i in np.flatnonzero(~X["usdc"] & np.isfinite(SC) & (SC >= thr) & (T >= ts(2022))):
        sym = X["names"][X["sym"][i]]; s = int(X["side"][i]); t = int(T[i])
        if sym not in cache:
            Tb, O, H, L, C, V = Em.load15(sym); cache[sym] = (Tb, O, H, L, C, Em.wilder(H, L, C, 14), {int(x): j for j, x in enumerate(Tb)})
        Tb, O, H, L, C, atr, pos = cache[sym]; bi = pos[t]; a = float(atr[bi])
        lv = ((L[bi] if s > 0 else H[bi]) if anchor == "wick" else C[bi]) - s * depth * a
        fb = next((b for b in range(bi + 1, min(len(C), bi + 1 + alive)) if ((L[b] <= lv) if s > 0 else (H[b] >= lv))), -1)
        if fb < 0: continue
        fill = min(lv, O[fb]) if s > 0 else max(lv, O[fb])
        T1, O1, H1_, L1, C1 = h1c(sym); j0, j1 = int(np.searchsorted(T1, Tb[fb])), int(np.searchsorted(T1, Tb[fb] + tfh * 3600))
        i1 = next((b for b in range(j0, j1) if ((L1[b] <= lv) if s > 0 else (H1_[b] >= lv))), -1)
        if i1 < 0: continue
        out.append(dict(key=(int(T1[i1]), s * (O1[i1] - lv) / a, -float(SC[i]), t), sym=sym, s=s, fill=fill, a=a, i1=i1, fbt=int(Tb[fb]), nb=fb - bi, tfh=tfh, pq=float(pq[i])))
    return out
EQ = events_q("s23_4h", 2, "s26_s23_4h_w1_0.npz", "s23_engine", 4, "wick", 1.0, 0.98) + events_q("s21h2", 0, "s26_s21h2_d2_1.npz", "s21h2_engine", 2, "close", 2.0, 0.98)
print("кандидаты q>=0.98", len(EQ), "из них q>=0.99", sum(e["pq"] >= 0.99 for e in EQ), flush=True)
WT = {}
for e in EQ:
    s_ = GH.dname(e["sym"].replace("USDT", "_USDT")) or (e["sym"] if os.path.exists(f"data/1h/{e['sym']}.csv") else None)
    if not s_: e["wt"] = np.nan; continue
    et, st_ = GH.coin(s_)["1d"]; k = np.searchsorted(et, e["key"][0], side="right") - 1
    e["wt"] = float(st_["wt"][k]) * e["s"] if k >= 60 else np.nan
print("wt найден", np.mean([np.isfinite(e["wt"]) for e in EQ]).round(3), flush=True)
fx = mk2(2.0, 3.0, lambda e: e["tfh"])
def run_sel(nm, keep):
    P = pool([e for e in EQ if keep(e)], fx)
    A = np.array([p[:5] for p in P], float); t0, t1, R, STv, K = A.T; sth = STv * 1.5
    n = np.array([int(np.sum((t0[:i] <= t0[i]) & (t1[:i] > t0[i]))) for i in range(len(t0))])
    wt = np.array([p[5]["wt"] for p in P]); osc = np.where(wt <= -3, 1.25, np.where(wt >= 22, 0.85, 1.0))
    W = np.where(n < 5, 0.625, 1.25) * osc
    y = np.array([sim_w(t0, t1, R, STv, sth, W, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.025) for s_ in roll])
    l12 = sim_w(t0, t1, R, STv, sth, W, int(np.searchsorted(t0, ts(2025, 10))), ts(2026, 10), 20, 0.04, -0.025)
    yr = t0.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970
    print(f"{nm:46s} n{len(R):5d} {R.mean():+.3f}R | медиана ${np.median(y[:, 0]):>6,.0f} 10% ${np.percentile(y[:, 0], 10):>5,.0f} 90% ${np.percentile(y[:, 0], 90):>6,.0f} просадка {np.median(y[:, 1])*100:.0f}% | 12 мес ${l12[0]:,.0f} | "
          + " ".join(f"{Y % 100}:{R[yr == Y].mean():+.2f}" for Y in range(2022, 2027)), flush=True)
run_sel("сейчас (q≥0.99)", lambda e: e["pq"] >= 0.99)
for ql in (0.98, 0.985):
    run_sel(f"против ≤-3: q≥{ql}, иначе q≥0.99", lambda e, ql=ql: e["pq"] >= (ql if e["wt"] <= -3 else 0.99))
    run_sel(f"против: q≥{ql}; по ходу ≥22: q≥0.995", lambda e, ql=ql: e["pq"] >= (ql if e["wt"] <= -3 else (0.995 if e["wt"] >= 22 else 0.99)))
run_sel("по ходу ≥22: q≥0.995, иначе 0.99", lambda e: e["pq"] >= (0.995 if e["wt"] >= 22 else 0.99))
