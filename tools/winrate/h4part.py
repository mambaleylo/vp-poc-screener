"""4h wick1 q0.99 fills: partial takes (and the stop to breakeven after the first take); WR = the first take reached,
'без минуса' = the trade closed >= 0; per set and the last 12 months; money up to 20 at 3%"""
import numpy as np, pickle, warnings; warnings.filterwarnings("ignore")
from numba import njit
import pool as PL, s20h4_engine as E
from mk import ts
F = pickle.load(open("h4fills.pkl", "rb"))
@njit
def sim(O, H, L, C, f, side, fill, atr, tks, frs, st, hold, be):
    n = len(C); risk = st * atr; sl = fill - side * risk
    e = min(n, f + hold); left = 1.0; pnl = 0.0; fees = 0.0002 * fill; first = 0; nxt = 0; k_end = e - 1 - f
    for q in range(e - f):
        b = f + q
        if (side > 0 and L[b] <= sl) or (side < 0 and H[b] >= sl):
            gap = (side > 0 and O[b] <= sl) or (side < 0 and O[b] >= sl)
            ex = O[b] if (gap and q > 0) else sl
            pnl += left * side * (ex - fill); fees += left * 0.0005 * fill; left = 0.0; k_end = q; break
        if q > 0:
            while nxt < len(tks):
                tp = fill + side * tks[nxt] * atr
                if (side > 0 and H[b] >= tp) or (side < 0 and L[b] <= tp):
                    pnl += frs[nxt] * side * (tp - fill); fees += frs[nxt] * 0.0002 * fill; left -= frs[nxt]; nxt += 1; first = 1
                    if be > 0: sl = fill + side * 0.0005 * fill   # the stop to the entry (+ the fees)
                else: break
            if left <= 1e-9: k_end = q; break
    if left > 1e-9:
        pnl += left * side * (C[e - 1] - fill); fees += left * 0.0005 * fill
    fees += 0.0003 * (k_end + 1) / 6.0 * fill
    return (pnl - fees) / risk, first, k_end + 1
cache = {}
V = [("тейк 1 (как сейчас)", [1.0], [1.0], 0), ("½ на 0.5 + ½ на 1", [0.5, 1.0], [0.5, 0.5], 0), ("½ на 0.5 + ½ на 1, потом безубыток", [0.5, 1.0], [0.5, 0.5], 1),
     ("⅓ 0.5 / ⅓ 1 / ⅓ 1.5", [0.5, 1.0, 1.5], [1/3, 1/3, 1/3], 0), ("⅓ 0.5 / ⅓ 1 / ⅓ 1.5, безубыток", [0.5, 1.0, 1.5], [1/3, 1/3, 1/3], 1),
     ("½ на 0.75 + ½ на 1.25", [0.75, 1.25], [0.5, 0.5], 0), ("½ на 0.75 + ½ на 1.25, безубыток", [0.75, 1.25], [0.5, 0.5], 1),
     ("тейк 0.75", [0.75], [1.0], 0), ("тейк 0.5", [0.5], [1.0], 0)]
roll = np.arange(ts(2024), ts(2025, 10) + 1, 7 * 86400.0)
for nm, tks, frs, be in V:
    rows = []
    for sym, fb, s, fill, a, t, pt in F:
        if sym not in cache: cache[sym] = E.load15(sym)
        Tb, O, H, L, C, Vv = cache[sym]
        r, w, k = sim(O, H, L, C, fb, s, fill, a, np.array(tks), np.array(frs), 2.0, 32, be)
        rows.append((t, t + k * 14400, float(r), 2.0 * a / fill, pt, w))
    rows.sort(); t0 = np.array([r[0] for r in rows], float); t1 = np.array([r[1] for r in rows], float)
    R = np.array([r[2] for r in rows]); ST = np.array([r[3] for r in rows]); W = np.array([r[5] for r in rows])
    un = np.array([r[4] != "train" for r in rows]); h = t0 >= ts(2025, 10)
    o = np.array([PL.multi(t0, t1, R, ST, int(np.searchsorted(t0, s)), s + 365 * 86400.0, 20, 0.03, False, -0.025) for s in roll]) + 100
    o6 = np.array([PL.multi(t0, t1, R, ST, int(np.searchsorted(t0, s)), s + 182 * 86400.0, 20, 0.03, False, -0.025) for s in roll]) + 100
    last = PL.multi(t0, t1, R, ST, int(np.searchsorted(t0, ts(2025, 10))), ts(2025, 10) + 365 * 86400.0, 20, 0.03, False, -0.025) + 100
    print(f"{nm:36s} невид: WR {W[un].mean()*100:3.0f}% без минуса {np.mean(R[un] >= 0)*100:3.0f}% {R[un].mean():+.3f}R | посл.12м WR {W[un&h].mean()*100:3.0f}% {R[un&h].mean():+.3f}R"
          f" || $100 → посл.12м ${last:,.0f}, год медиана ${np.median(o):,.0f} хуже-10% ${np.percentile(o,10):,.0f}, 6м ниже $100 {np.mean(o6<100)*100:.0f}%", flush=True)
