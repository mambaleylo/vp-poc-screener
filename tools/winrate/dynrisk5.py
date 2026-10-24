"""dynrisk5: ⚡ the load counted on the same side only / both sides split; smooth 3-step scales — vs v703 (<5 all: x0.625 / x1.25)"""
exec(open("dynrisk4.py").read().split("for nm, lv, rk in")[0])
NSIDE = np.zeros(len(T0_), np.int64); NOPP = np.zeros(len(T0_), np.int64)
for i in range(len(T0_)):
    on_ = (T0_[:i] <= T0_[i]) & (T1_[:i] > T0_[i]); NSIDE[i] = int(np.sum(on_ & (SD[:i] == SD[i]))); NOPP[i] = int(np.sum(on_ & (SD[:i] != SD[i])))
yr = T0_.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970
for nm, n in (("same side", NSIDE), ("opposite", NOPP)):
    for Y in range(2022, 2027):
        m = yr == Y; c = [(n < 3), (n >= 3) & (n < 8), (n >= 8)]
        print(nm, Y, " · ".join(f"{l}: {R_[m & cc].mean() if (m&cc).sum() else np.nan:+.3f} ({(m & cc).sum()})" for l, cc in zip(("0–2", "3–7", "8+"), c)), flush=True)
def runW(nm, W):
    W = W * len(W) / W.sum() if False else W
    y = np.array([sim_w(T0_, T1_, R_, ST_, STH_, W, int(np.searchsorted(T0_, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.025) for s_ in roll])
    l12 = sim_w(T0_, T1_, R_, ST_, STH_, W, int(np.searchsorted(T0_, ts(2025, 10))), ts(2026, 10), 20, 0.04, -0.025)
    print(f"{nm:44s} ср.вес {W.mean():.2f} медиана ${np.median(y[:, 0]):>6,.0f} 10% ${np.percentile(y[:, 0], 10):>5,.0f} 90% ${np.percentile(y[:, 0], 90):>6,.0f} просадка {np.median(y[:, 1])*100:.0f}% | 12 мес ${l12[0]:,.0f}", flush=True)
step = lambda n, thr, lo, hi: np.where(n < thr, lo, hi)
runW("v703: все <5 x0.625, иначе x1.25", step(NOPEN, 5, 0.625, 1.25))
for thr in (2, 3, 4):
    runW(f"та же сторона <{thr} x0.625, иначе x1.25", step(NSIDE, thr, 0.625, 1.25))
runW("3 ступени: <3 x0.5, <8 x1.0, иначе x1.5", np.where(NOPEN < 3, 0.5, np.where(NOPEN < 8, 1.0, 1.5)))
runW("3 ступени: <3 x0.5, <6 x1.0, иначе x1.25", np.where(NOPEN < 3, 0.5, np.where(NOPEN < 6, 1.0, 1.25)))
runW("плавно: 0.5 + 0.1*n, макс 1.5", np.minimum(1.5, 0.5 + 0.1 * NOPEN))
runW("v703 + встречные ≥3 → x0.8", step(NOPEN, 5, 0.625, 1.25) * np.where(NOPP >= 3, 0.8, 1.0))
