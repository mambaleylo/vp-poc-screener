"""EMA night round: a partial take (a share off at +x R, the stop of the rest to the fill), caps — on the deployed rule
(longs, EMA200 < 10 daily ATR, 4h score +0.1, BTC above EMA50; stop 0.75 daily ATR, take 3R, 72 h)"""
import sys, numpy as np, pandas as pd
ARGS = sys.argv[1:]
from numba import njit
import ema_h as E
d = E.d
@njit(cache=True)
def simp(O, H, L, C, j, side, fill, datr, a, take, hold, pa, pf):
    n = len(C); risk = fill * a * datr / 100
    stop = fill - side * risk; tp = fill + side * take * risk; pt = fill + side * pa * risk; took = False
    e = min(n, j + hold); k = e - 1 - j; ex = C[e - 1]; kind = 3
    for q in range(e - j):
        b = j + q
        if (side > 0 and L[b] <= stop) or (side < 0 and H[b] >= stop):
            gap = (side > 0 and O[b] <= stop) or (side < 0 and O[b] >= stop)
            ex = O[b] if (gap and q > 0) else stop; k = q; kind = 4 if took else 0; break
        if pa > 0 and q > 0 and not took and ((side > 0 and H[b] >= pt) or (side < 0 and L[b] <= pt)):
            took = True; stop = fill
        if q > 0 and ((side > 0 and H[b] >= tp) or (side < 0 and L[b] <= tp)):
            ex = tp; k = q; kind = 2; break
    fee = (0.001 + 0.0003 * (k + 1) / 24) * fill / risk
    rest = side * (ex - fill) / risk
    return ((pf * pa + (1 - pf) * rest) if took else rest) - fee, k + 1, kind
def outcomes(idx, a=0.75, take=3.0, hold=72, pa=0.0, pf=0.33):
    R = np.full(len(d), np.nan); K = np.zeros(len(d), np.int64); KD = np.full(len(d), -1)
    sym, j, side, lv, datr = d.sym.values, d.j.values, d.side.values, d.lv.values, d.datr.values
    for i in idx:
        O, H, L, C = E.bars(sym[i])
        R[i], K[i], KD[i] = simp(O, H, L, C, int(j[i]), int(side[i]), float(lv[i]), float(datr[i]), a, take, hold, pa, pf)
    return R, K, KD
side, tf, e200 = d.side.values, d.tf_s.values, d.s_d_ema200.values
bema = pd.read_parquet(f"{E.D}/er_all.parquet", columns=["s_b_ema50"]).s_b_ema50.values
for q in (0.97, 0.90):
    target = 0.45 if q >= 0.97 else 0.50
    grid = tuple(np.round(np.arange(0.0025, 0.1, 0.0025), 4)) if q >= 0.97 else tuple(np.round(np.arange(0.001, 0.03, 0.001), 4))
    thr = np.array([E.THR[y][q] if y in E.THR else np.inf for y in E.YR]); rel = E.SC - thr
    NOW = (side > 0) & (e200 < 10) & ((tf != "4h") | (rel >= 0.1)) & (bema > 0)
    idx = E.cand(q, NOW)
    print(f"\n=== EMA q{q}")
    for nm, kw, cap in (("сейчас (стоп 0.75, тейк 3R)", {}, 12), ("1/3 на +1R → б/у", dict(pa=1.0), 12), ("1/2 на +1R → б/у", dict(pa=1.0, pf=0.5), 12),
                        ("1/3 на +0.7R → б/у", dict(pa=0.7), 12), ("1/3 на +1.5R → б/у", dict(pa=1.5), 12), ("1/4 на +1R → б/у", dict(pa=1.0, pf=0.25), 12),
                        ("1/3 на +1R, тейк 4R", dict(pa=1.0, take=4.0), 12),
                        ("не больше 4 сделок", {}, 4), ("не больше 6", {}, 6), ("не больше 8", {}, 8)):
        R, K, KD = outcomes(idx, **kw); tr = E.replay(idx, R, K, cap=cap)
        r = R[tr]; E.line(f"{nm} (минусов {np.mean(r < 0)*100:.0f}%)", tr, R, K, KD, target, grid)
