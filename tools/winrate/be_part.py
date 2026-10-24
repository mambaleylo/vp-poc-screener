"""⚡ exits: the stop to the entry after the price went be x ATR our way (from the next hour), and / or half off at pt x ATR —
on top of the v0.99.704 exits (take 1.1, the 2 ATR close stop of the chart's candle, the emergency 3 ATR, 32 bars) and risk rules"""
exec(open("osc_take.py").read().split("run(\"v704: тейк 1.1 везде\"")[0])
@njit
def walk6(T, O, H, L, C, i1, end_t, s, fill, a, tk, soft, hard, kh, size_by, be, pt):
    risk = size_by * a; hsl = fill - s * hard * a; ssl = fill - s * soft * a; tp1 = fill + s * tk * a
    bel = fill + s * 0.001 * fill; armed = False; half = 0.0; ptp = fill + s * pt * a
    b = i1
    while b < len(C) and T[b] < end_t:
        q = b - i1; fee = (0.0007 + 0.0003 * (q + 1) / 24) * fill
        if (s > 0 and L[b] <= hsl) or (s < 0 and H[b] >= hsl):
            x = O[b] if (q > 0 and ((s > 0 and O[b] <= hsl) or (s < 0 and O[b] >= hsl))) else hsl
            return half + (1 - (0.5 if half != 0 else 0)) * (s * (x - fill) - fee) / risk, 0, T[b] + 3600
        if armed and ((s > 0 and L[b] <= bel) or (s < 0 and H[b] >= bel)):
            x = O[b] if ((s > 0 and O[b] <= bel) or (s < 0 and O[b] >= bel)) else bel
            return half + (1 - (0.5 if half != 0 else 0)) * (s * (x - fill) - fee) / risk, 5, T[b] + 3600
        if q > 0 and pt > 0 and half == 0 and ((s > 0 and H[b] >= ptp) or (s < 0 and L[b] <= ptp)):
            half = 0.5 * (s * (ptp - fill) - (0.0004 + 0.0003 * (q + 1) / 24) * fill) / risk
        if q > 0 and ((s > 0 and H[b] >= tp1) or (s < 0 and L[b] <= tp1)):
            return half + (1 - (0.5 if half != 0 else 0)) * (s * (tp1 - fill) - (0.0004 + 0.0003 * (q + 1) / 24) * fill) / risk, 1, T[b] + 3600
        if (T[b] + 3600) % (kh * 3600) == 0 and ((s > 0 and C[b] <= ssl) or (s < 0 and C[b] >= ssl)):
            return half + (1 - (0.5 if half != 0 else 0)) * (s * (C[b] - fill) - fee) / risk, 4, T[b] + 3600
        if be > 0 and ((s > 0 and H[b] - fill >= be * a) or (s < 0 and fill - L[b] >= be * a)): armed = True
        b += 1
    b = min(b, len(C)) - 1
    return half + (1 - (0.5 if half != 0 else 0)) * (s * (C[b] - fill) - (0.0007 + 0.0003 * (b - i1 + 1) / 24) * fill) / risk, 3, T[b] + 3600
def fb(be, pt):
    def f(e):
        T, O, H, L, C = h1c(e["sym"])
        return walk6(T, O, H, L, C, e["i1"], e["fbt"] + 32 * e["tfh"] * 3600, e["s"], e["fill"], e["a"], 1.1, 2.0, 3.0, e["tfh"], 2.0, be, pt)
    return f
run("v704 (без безубытка и частичной)", fb(0.0, 0.0))
for be in (0.5, 0.7, 0.9):
    run(f"безубыток после +{be} ATR", fb(be, 0.0))
for pt in (0.5, 0.7):
    run(f"половина на +{pt} ATR", fb(0.0, pt))
run("половина на +0.6 и безубыток после +0.6", fb(0.6, 0.6))
