"""the user: "первые 2 свечи считая свечу входа, пока цена в этом диапазоне, ставить стоп очень маленьким ... хотя бы
половина обычного стопа" — the v0.99.695 exits (the take 1.1, the chart candle's close beyond 2 ATR, the emergency 3) plus
an early stop: during the first n chart candles (the fill's candle counted) a tight stop at d ATR — by a touch, by a 1h close
or by the chart candle's close; the position sized by the 2 ATR stop as before. The 4h + 2h pool, honest order, the bot's
leverage (the liquidation 1.25x the emergency stop)"""
exec(open("closetf7.py").read().split("def money3")[0])
@njit
def walk6(T, O, H, L, C, i1, end_t, s, fill, a, tk, soft, hard, kh, early_end, ed, emode):
    risk = soft * a; hsl = fill - s * hard * a; ssl = fill - s * soft * a; tp1 = fill + s * tk * a; esl = fill - s * ed * a
    b = i1
    while b < len(C) and T[b] < end_t:
        q = b - i1
        if (s > 0 and L[b] <= hsl) or (s < 0 and H[b] >= hsl):
            x = O[b] if (q > 0 and ((s > 0 and O[b] <= hsl) or (s < 0 and O[b] >= hsl))) else hsl
            return (s * (x - fill) - (0.0007 + 0.0003 * (q + 1) / 24) * fill) / risk, 0, T[b] + 3600
        early = T[b] < early_end
        if early and emode == 0 and ((s > 0 and L[b] <= esl) or (s < 0 and H[b] >= esl)):   # by a touch (a stop order)
            x = O[b] if (q > 0 and ((s > 0 and O[b] <= esl) or (s < 0 and O[b] >= esl))) else esl
            return (s * (x - fill) - (0.0007 + 0.0003 * (q + 1) / 24) * fill) / risk, 5, T[b] + 3600
        if q > 0 and ((s > 0 and H[b] >= tp1) or (s < 0 and L[b] <= tp1)):
            return (s * (tp1 - fill) - (0.0004 + 0.0003 * (q + 1) / 24) * fill) / risk, 1, T[b] + 3600
        if early and emode > 0 and (emode == 1 or (T[b] + 3600) % (kh * 3600) == 0) and ((s > 0 and C[b] <= esl) or (s < 0 and C[b] >= esl)):
            return (s * (C[b] - fill) - (0.0007 + 0.0003 * (q + 1) / 24) * fill) / risk, 5, T[b] + 3600
        if (T[b] + 3600) % (kh * 3600) == 0 and ((s > 0 and C[b] <= ssl) or (s < 0 and C[b] >= ssl)):
            return (s * (C[b] - fill) - (0.0007 + 0.0003 * (q + 1) / 24) * fill) / risk, 4, T[b] + 3600
        b += 1
    b = min(b, len(C)) - 1
    return (s * (C[b] - fill) - (0.0007 + 0.0003 * (b - i1 + 1) / 24) * fill) / risk, 3, T[b] + 3600
def mk6(n, ed, emode):
    def f(e):
        T, O, H, L, C = h1c(e["sym"]); bs = e["tfh"] * 3600
        return walk6(T, O, H, L, C, e["i1"], e["fbt"] + 32 * bs, e["s"], e["fill"], e["a"], 1.1, 2.0, 3.0, e["tfh"], e["fbt"] + n * bs, ed, emode)
    return f
def money6(nm, P, ref=None):
    A = np.array([p[:5] for p in P], float); t0, t1, R, STv, K = A.T; STH = STv * 1.5
    y = np.array([sim_125(t0, t1, R, STv, STH, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.025) for s_ in roll])
    yh = np.array([sim_125(t0, t1, R, STv, STH, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.04)[0] for s_ in roll])
    l12 = sim_125(t0, t1, R, STv, STH, int(np.searchsorted(t0, ts(2025, 10))), ts(2026, 10), 20, 0.04, -0.025)
    yrs = (t0.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970)
    ys = " ".join(f"{Y % 100}:{R[yrs == Y].mean():+.2f}" for Y in range(2022, 2027))
    ex = "" if ref is None else f" | окон лучше {np.mean(y[:, 0] > ref)*100:.0f}%"
    print(f"{nm:40s} WR {np.mean(K == 1)*100:.0f}% {R.mean():+.3f}R ранних {np.mean(K == 5)*100:.0f}% | медиана ${np.median(y[:, 0]):>6,.0f} 10% ${np.percentile(y[:, 0], 10):>5,.0f} "
          f"просадка {np.median(y[:, 1])*100:.0f}% жёстко ${np.median(yh):,.0f} | 12 мес ${l12[0]:,.0f} | {ys}{ex}", flush=True)
    return y[:, 0]
r0 = money6("сейчас (695)", pool(E, mk6(0, 2.0, 0)))
for emode, mn in ((0, "касанием"), (1, "закр. часа"), (2, "закр. свечи графика")):
    print(f"== ранний стоп {mn}")
    for n in (1, 2, 3):
        for ed in (0.5, 0.75, 1.0, 1.25, 1.5):
            if emode == 2 and n == 1 and ed > 1.0: continue
            money6(f"первые {n} св., стоп {ed} ATR", pool(E, mk6(n, ed, emode)), r0)
