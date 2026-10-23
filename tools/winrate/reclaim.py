"""the user: "перезаход на возврате на точку стопа — вход на старом стопе, тейк как раньше, стоп короткий". After a ⚡
stop (2 ATR, intrabar): a stop order at the old stop's price for the bars after the stop bar (the price comes back up
for a long); take = the old take or k ATR from the entry; the stop 0.5 / 1 ATR below the entry or below the sweep's
low; R per its own stop; out after 32 bars"""
import numpy as np, warnings; warnings.filterwarnings("ignore")
exec(open("stopcheck.py").read().split("# (1) the stopped")[0])
def run(O, H, L, C, f, s, px, tp, sl, hold):
    e = min(len(C), f + hold); risk = abs(px - sl)
    for q in range(e - f):
        b = f + q
        if (L[b] <= sl) if s > 0 else (H[b] >= sl):
            ex = O[b] if (q > 0 and ((O[b] <= sl) if s > 0 else (O[b] >= sl))) else sl
            return (s * (ex - px) - (0.0005 + 0.0005 + 0.0003 * (q + 1) / 6) * px) / risk, 0
        if q > 0 and ((H[b] >= tp) if s > 0 else (L[b] <= tp)):
            return (s * (tp - px) - (0.0005 + 0.0002 + 0.0003 * (q + 1) / 6) * px) / risk, 1
    return (s * (C[e - 1] - px) - (0.0005 + 0.0005 + 0.0003 * (e - f) / 6) * px) / risk, 0
res = {}
for sym, fb, s, fill, a, t, un in TR_:
    Tb, O, H, L, C, V = bars(sym); sl0 = fill - s * 2 * a; tp0 = fill + s * a
    e = min(len(C), fb + 32); b = None
    for q in range(e - fb):
        x = fb + q
        if (L[x] <= sl0) if s > 0 else (H[x] >= sl0): b = x; break
        if q > 0 and ((H[x] >= tp0) if s > 0 else (L[x] <= tp0)): break
    if b is None or b + 1 >= len(C): continue
    yr = int(Tb[b]) // 31557600 + 1970
    for W in (4, 8, 16):
        # the reclaim: a bar after the stop bar trades back through the old stop (a stop-market order there)
        f2 = next((x for x in range(b + 1, min(b + 1 + W, len(C))) if ((H[x] >= sl0) if s > 0 else (L[x] <= sl0))), None)
        if f2 is None: continue
        px = max(sl0, O[f2]) if s > 0 else min(sl0, O[f2])   # a gap through it fills at the open
        low = (L[b:f2 + 1].min() if s > 0 else H[b:f2 + 1].max())
        for tpn, tp in (("тейк прежний", tp0), ("тейк 1 ATR", px + s * a), ("тейк 1.5 ATR", px + s * 1.5 * a), ("тейк 2 ATR", px + s * 2 * a)):
            if s * (tp - px) <= 0: continue
            for sln, sl in (("стоп 0.5 ATR", px - s * 0.5 * a), ("стоп 1 ATR", px - s * a), ("стоп под минимум выноса", low - s * 0.1 * a)):
                if s * (px - sl) <= 0.05 * a: continue
                r, w = run(O, H, L, C, f2, s, px, tp, sl, 32)
                res.setdefault((W, tpn, sln), []).append((yr, r, w, un))
rows = []
for k, v in res.items():
    yrs = np.array([x[0] for x in v]); R = np.array([x[1] for x in v]); W_ = np.array([x[2] for x in v]); U = np.array([x[3] for x in v])
    rows.append((R.mean(), k, len(R), W_.mean(), R[U].mean() if U.any() else np.nan, " ".join(f"{y}:{R[yrs == y].mean():+.2f}" for y in range(2022, 2027) if (yrs == y).any())))
rows.sort(key=lambda x: -x[0])
for m, k, n, wr, mu, by in rows:
    print(f"ждать {k[0]:2d} св · {k[1]:13s} · {k[2]:24s}: n{n:3d} WR {wr*100:3.0f}% {m:+.3f}R (невид {mu:+.3f}R) [{by}]")
