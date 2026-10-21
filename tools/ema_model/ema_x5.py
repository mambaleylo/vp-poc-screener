"""📐 EMA, night round 3 on the v0.99.664 rule (the limit 0.2 daily ATR past the EMA, filled in the touch hour only):
keep the limit for up to W more hours within the same candle (the level is fixed till the candle closes), and a ladder
(half at the EMA, half deeper)"""
import numpy as np, pandas as pd, datetime as dt
from numba import njit
import ema_h as E
@njit(cache=True)
def simp(O, H, L, C, j, side, fill, datr, a, take, hold, pa, pf, pa2, pf2, lock_at, lock_to):
    n = len(C); risk = fill * a * datr / 100
    stop = fill - side * risk; tp = fill + side * take * risk; took = False; took2 = False; locked = False
    e = min(n, j + hold); k = e - 1 - j; ex = C[e - 1]
    for q in range(e - j):
        b = j + q
        if (side > 0 and L[b] <= stop) or (side < 0 and H[b] >= stop):
            gap = (side > 0 and O[b] <= stop) or (side < 0 and O[b] >= stop)
            ex = O[b] if (gap and q > 0) else stop; k = q; break
        if q > 0:
            fav = ((H[b] - fill) if side > 0 else (fill - L[b])) / risk
            if pa > 0 and not took and fav >= pa: took = True; stop = fill
            if pa2 > 0 and took and not took2 and fav >= pa2: took2 = True
            if lock_at > 0 and not locked and fav >= lock_at: locked = True; stop = fill + side * lock_to * risk
            if fav >= take: ex = tp; k = q; break
    fee = (0.001 + 0.0003 * (k + 1) / 24) * fill / risk
    rest = side * (ex - fill) / risk
    if not took: return rest - fee, k + 1
    if not took2: return pf * pa + (1 - pf) * rest - fee, k + 1
    return pf * pa + pf2 * pa2 + (1 - pf - pf2) * rest - fee, k + 1
d = E.d
side, tf, e200 = d.side.values, d.tf_s.values, d.s_d_ema200.values
bema = pd.read_parquet(f"{E.D}/er_all.parquet", columns=["s_b_ema50"]).s_b_ema50.values
def cend(t, f):
    if f == "4h": return (t // 14400 + 1) * 14400
    if f == "1d": return (t // 86400 + 1) * 86400
    if f == "1w": return ((t - 345600) // 604800 + 1) * 604800 + 345600
    x = dt.datetime.fromtimestamp(int(t), dt.timezone.utc); y, m = (x.year + 1, 1) if x.month == 12 else (x.year, x.month + 1)
    return int(dt.datetime(y, m, 1, tzinfo=dt.timezone.utc).timestamp())
def outcomes(idx, deep=0.2, wait=1, ladder=0.0, take=4.0):
    """wait = how many hours from the touch hour the deep limit stays (bounded by the candle's close);
    ladder > 0: half at the EMA (the touch), half at `ladder` daily ATR deeper — R = the mean of the two halves"""
    R = np.full(len(d), np.nan); K = np.zeros(len(d), np.int64); KD = np.full(len(d), -1)
    sym, j, lv, datr, T = d.sym.values, d.j.values, d.lv.values, d.datr.values, E.T
    for i in idx:
        s = int(side[i]); dr = float(datr[i]); j0 = int(j[i]); O, H, L, C = E.bars(sym[i])
        def leg(dp, w):
            thr = lv[i] * (1 - s * (0.1 + dp) / 100); fill = lv[i] * (1 - s * dp / 100)
            nb = min(w, int((cend(int(T[i]), tf[i]) - int(T[i])) // 3600), len(L) - j0)
            for q in range(nb):
                b = j0 + q
                if (s > 0 and L[b] <= thr) or (s < 0 and H[b] >= thr):
                    r, k = simp(O, H, L, C, b, s, fill, dr, 0.75, take, 72, 1.0, 0.33, 0.0, 0.0, 0.0, 0.0)
                    return r, k + q
            return None
        if ladder > 0:
            a = leg(0.0, 1)
            if a is None: continue
            b_ = leg(ladder * dr, wait)
            R[i] = 0.5 * a[0] + 0.5 * (b_[0] if b_ else 0.0); K[i] = max(a[1], b_[1] if b_ else 0)
        else:
            a = leg(deep * dr, wait)
            if a is None: continue
            R[i], K[i] = a
    return R, K, KD
V = [("глубже 0.2, только час касания (v664)", {}), ("глубже 0.2, ждать до 3ч", dict(wait=3)), ("глубже 0.2, ждать до 6ч", dict(wait=6)),
     ("глубже 0.2, до конца свечи", dict(wait=10**6)), ("глубже 0.3, до конца свечи", dict(deep=0.3, wait=10**6)),
     ("глубже 0.25, ждать до 6ч", dict(deep=0.25, wait=6)),
     ("лесенка: ½ на EMA + ½ глубже 0.3 (час)", dict(ladder=0.3)), ("лесенка: ½ на EMA + ½ глубже 0.3 (до конца свечи)", dict(ladder=0.3, wait=10**6))]
for q in (0.97, 0.90):
    target = 0.45 if q >= 0.97 else 0.50
    grid = tuple(np.round(np.arange(0.0025, 0.1, 0.0025), 4)) if q >= 0.97 else tuple(np.round(np.arange(0.001, 0.03, 0.001), 4))
    thr = np.array([E.THR[y][q] if y in E.THR else np.inf for y in E.YR]); rel = E.SC - thr
    m = (side > 0) & (e200 < 10) & ((tf != "4h") | (rel >= 0.1)) & (bema > 0)
    idx = E.cand(q, m)
    print(f"\n=== EMA q{q}", flush=True)
    for nm, kw in V:
        R, K, KD = outcomes(idx, **kw); tr = E.replay(idx, R, K)
        r = R[tr]; E.line(f"{nm} (минусов {np.mean(r < 0)*100:.0f}%)", tr, R, K, KD, target, grid)
