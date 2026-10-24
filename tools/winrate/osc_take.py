"""⚡ take by the daily WaveTrend: against the trade (wt1 x side <= -3) a farther take, with it (>= 22) a nearer one; the pool,
the exits and money as v0.99.704 (the load and the WaveTrend risk rules)"""
exec(open("dynrisk4.py").read().split("for nm, lv, rk in")[0])
import gh_lib as GH
for e in E:
    s_ = GH.dname(e["sym"].replace("USDT", "_USDT")) or (e["sym"] if os.path.exists(f"data/1h/{e['sym']}.csv") else None)
    if not s_: e["wt"] = np.nan; continue
    et, st_ = GH.coin(s_)["1d"]; k = np.searchsorted(et, e["key"][0], side="right") - 1
    e["wt"] = float(st_["wt"][k]) * e["s"] if k >= 60 else np.nan
def fx(tk_a, tk_w, tk_m=1.1):
    def f(e):
        T, O, H, L, C = h1c(e["sym"]); w = e["wt"]
        tk = tk_a if w <= -3 else (tk_w if w >= 22 else tk_m)
        return walk5(T, O, H, L, C, e["i1"], e["fbt"] + 32 * e["tfh"] * 3600, e["s"], e["fill"], e["a"], tk, 2.0, 3.0, e["tfh"], 2.0)
    return f
def run(nm, f):
    P = pool(E, f)
    A = np.array([p[:5] for p in P], float); t0, t1, R, STv, K = A.T; sth = STv * 1.5
    n = np.array([int(np.sum((t0[:i] <= t0[i]) & (t1[:i] > t0[i]))) for i in range(len(t0))])
    wt = np.array([p[5]["wt"] for p in P]); W = np.where(n < 5, 0.625, 1.25) * np.where(wt <= -3, 1.25, np.where(wt >= 22, 0.85, 1.0))
    y = np.array([sim_w(t0, t1, R, STv, sth, W, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.025) for s_ in roll])
    l12 = sim_w(t0, t1, R, STv, sth, W, int(np.searchsorted(t0, ts(2025, 10))), ts(2026, 10), 20, 0.04, -0.025)
    yr = t0.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970
    print(f"{nm:34s} n{len(R):5d} WR {np.mean(K == 1)*100:.0f}% {R.mean():+.3f}R | медиана ${np.median(y[:, 0]):>6,.0f} 10% ${np.percentile(y[:, 0], 10):>5,.0f} 90% ${np.percentile(y[:, 0], 90):>6,.0f} просадка {np.median(y[:, 1])*100:.0f}% | 12 мес ${l12[0]:,.0f} | "
          + " ".join(f"{Y % 100}:{R[yr == Y].mean():+.2f}" for Y in range(2022, 2027)), flush=True)
run("v704: тейк 1.1 везде", fx(1.1, 1.1))
for a_ in (1.3, 1.5, 2.0):
    run(f"против: тейк {a_}", fx(a_, 1.1))
for w_ in (0.9, 0.8):
    run(f"по ходу: тейк {w_}", fx(1.1, w_))
run("против 1.5, по ходу 0.9", fx(1.5, 0.9))
