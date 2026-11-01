"""the short breakout's variants (rb_short.py): chosen on 2021-2023 (positive every year), checked on 2024-2026 (unseen).
One trade a coin at a time (a signal while the coin's trade is open is skipped) for the top ones. -> the table"""
import sys, os, numpy as np
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
import rb_short as RS


def P(tfh):
    """the grid rb_short.py used for this chart"""
    NS = (20, 30, 50) if tfh < 24 else (15, 20, 30)
    EX = ("t2", "t3", "dc10", "dc20", "p1t3", "p1dc10") + (("t5", "p1t5") if tfh >= 12 else ())
    return NS, EX, ((2, 5, 10) if tfh < 12 else (5, 10, 20))
YRS = list(range(2021, 2027)); TR, CK = (2021, 2022, 2023), (2024, 2025, 2026)
WK = {2021: 52, 2022: 52, 2023: 52, 2024: 52, 2025: 52, 2026: 43}


def year(t):
    return (1970 + (t / 86400 + 0.5) / 365.2425).astype(int)


def dedupe(sym, t, bars, tfh):
    """one trade a coin at a time -> the mask of the trades taken"""
    keep = np.zeros(len(t), bool); last = {}
    for k in np.lexsort((t, sym)):
        s_ = sym[k]
        if t[k] >= last.get(s_, -1):
            keep[k] = True; last[s_] = t[k] + bars[k] * tfh * 3600
    return keep


if __name__ != "__main__": raise SystemExit
rows = []
for tfh in (1, 2, 4, 12, 24):
    fn = f"{ST}/wf/rbs_{tfh}.npz"
    if not os.path.exists(fn): continue
    z = np.load(fn); y = z["y"]; yr = year(z["t"]); NS, EX, HD = P(tfh)
    for N in NS:
        for K in (2.0, 3.0, 4.0):
            m0 = (z["N"] == N) & (z["rg"] < K)
            for si, sk in enumerate(RS.STOPS):
                for xi, xn in enumerate(EX):
                    for hi, hd in enumerate(HD):
                        r = y[:, si, xi, hi, 0]; m = m0 & ~np.isnan(r)
                        av = {Y: (r[m & (yr == Y)].mean() if (m & (yr == Y)).sum() >= 20 else np.nan) for Y in YRS}
                        nw = {Y: (m & (yr == Y)).sum() / WK[Y] for Y in YRS}
                        rows.append((tfh, N, K, sk, xn, hd, av, nw, m))
print(len(rows), "variants")
ok = [v for v in rows if all(np.isfinite(v[6][Y]) and v[6][Y] > 0.03 for Y in TR)]
ok.sort(key=lambda v: -np.mean([v[6][Y] * v[7][Y] for Y in TR]))   # R a week on the training years
print(f"{len(ok)} positive in every training year")
cache = {}
print("tf N K stop exit hold | " + " ".join(f"{Y}" for Y in YRS) + " | R/нед 21-23 → 24-26 | сделок/нед | дней в сделке (медиана/90%)")
for v in ok[:int(os.environ.get('TOP', 25))]:
    tfh, N, K, sk, xn, hd, av, nw, m = v
    if tfh not in cache: cache[tfh] = np.load(f"{ST}/wf/rbs_{tfh}.npz")
    z = cache[tfh]; si, xi, hi = RS.STOPS.index(sk), P(tfh)[1].index(xn), P(tfh)[2].index(hd)
    idx = np.flatnonzero(m); r = z["y"][idx, si, xi, hi, 0]; b = z["y"][idx, si, xi, hi, 1]
    kp = dedupe(z["sym"][idx], z["t"][idx], b, tfh); r, b, yr = r[kp], b[kp], year(z["t"][idx][kp])
    a = {Y: r[yr == Y].mean() if (yr == Y).sum() else np.nan for Y in YRS}; w = {Y: (yr == Y).sum() / WK[Y] for Y in YRS}
    rw = lambda Ys: np.mean([a[Y] * w[Y] for Y in Ys])
    d = b * tfh / 24
    print(f"{tfh}h {N} {K:g} {sk:g} {xn} {hd}д | " + " ".join(f"{a[Y]:+.2f}" for Y in YRS) + f" | {rw(TR):+.2f} → {rw(CK):+.2f} | {np.mean([w[Y] for Y in YRS]):.1f} | {np.median(d):.1f}/{np.percentile(d, 90):.1f}", flush=True)
print("eval done")
