"""after a ⚡ stop: a second trade on its own (its own 2 ATR stop, the same ATR) — at the next bar's open, or a limit
deeper below the stop within 4 bars; take 1 ATR from it or the first trade's take; R per its 2 ATR stop"""
import numpy as np, warnings; warnings.filterwarnings("ignore")
exec(open("stopcheck.py").read().split("# (1) the stopped")[0])
def sim1(O, H, L, C, f, s, fill, a, tp, sl, hold):
    e = min(len(C), f + hold)
    for q in range(e - f):
        b = f + q
        if (L[b] <= sl) if s > 0 else (H[b] >= sl):
            ex = O[b] if (q > 0 and ((O[b] <= sl) if s > 0 else (O[b] >= sl))) else sl
            return (s * (ex - fill) - (0.0007 + 0.0003 * (q + 1) / 6) * fill) / abs(fill - sl), 0, b
        if q > 0 and ((H[b] >= tp) if s > 0 else (L[b] <= tp)):
            return (s * (tp - fill) - (0.0004 + 0.0003 * (q + 1) / 6) * fill) / abs(fill - sl), 1, b
    return (s * (C[e - 1] - fill) - (0.0007 + 0.0003 * (e - f) / 6) * fill) / abs(fill - sl), 0, e - 1
V = {"рынок след. свечи, тейк 1 ATR": [], "рынок, тейк = исходный": [], "лимитка на 0.5 ATR ниже стопа, тейк 1 ATR": [],
     "лимитка на 1 ATR ниже стопа, тейк 1 ATR": [], "лимитка 1 ATR ниже, тейк = исходный": []}
for sym, fb, s, fill, a, t, un in TR_:
    Tb, O, H, L, C, Vv = bars(sym); sl = fill - s * 2 * a; tp = fill + s * a
    r, w, b = sim1(O, H, L, C, fb, s, fill, a, tp, sl, 32)
    if w or not ((L[b] <= sl) if s > 0 else (H[b] >= sl)) or b + 1 >= len(C): continue   # only the stopped ones
    yr = int(Tb[b]) // 31557600 + 1970
    e1 = O[b + 1]
    for nm, (kind, dep, tpk) in {"рынок след. свечи, тейк 1 ATR": ("m", 0, "1"), "рынок, тейк = исходный": ("m", 0, "orig"),
                                 "лимитка на 0.5 ATR ниже стопа, тейк 1 ATR": ("l", 0.5, "1"), "лимитка на 1 ATR ниже стопа, тейк 1 ATR": ("l", 1.0, "1"),
                                 "лимитка 1 ATR ниже, тейк = исходный": ("l", 1.0, "orig")}.items():
        if kind == "m":
            f2, px = b + 1, e1
        else:
            lv2 = sl - s * dep * a
            f2 = next((x for x in range(b + 1, min(b + 5, len(C))) if ((L[x] <= lv2) if s > 0 else (H[x] >= lv2))), None)
            if f2 is None: continue
            px = min(lv2, O[f2]) if s > 0 else max(lv2, O[f2])
        tp2 = px + s * a if tpk == "1" else tp
        if s * (tp2 - px) <= 0: continue
        r2, w2, _ = sim1(O, H, L, C, f2, s, px, a, tp2, px - s * 2 * a, 32)
        V[nm].append((yr, r2, w2, un))
for nm, rows in V.items():
    yrs = np.array([r[0] for r in rows]); R = np.array([r[1] for r in rows]); W = np.array([r[2] for r in rows]); U = np.array([r[3] for r in rows])
    by = " ".join(f"{y}:{R[yrs == y].mean():+.2f}" for y in range(2022, 2027) if (yrs == y).any())
    print(f"{nm:44s} n{len(R)} WR {W.mean()*100:.0f}% {R.mean():+.3f}R (невид {R[U].mean():+.3f}R n{U.sum()}) [{by}]")
