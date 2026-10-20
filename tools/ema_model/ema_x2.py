"""📐 EMA, night round 2 on the v0.99.661 rule (longs, EMA200 < 10 daily ATR, 4h score +0.1, BTC above EMA50; stop 0.75 daily
ATR, 1/3 off at +1R → break-even, take 4R, 72 h): the stop, the take, the hold, a second partial, a lock after +2R, a limit
deeper past the EMA (filled in the touch hour), the EMA200 distance, the 4h margin, the score margin"""
import sys, numpy as np, pandas as pd
from numba import njit
import ema_h as E
d = E.d
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
def outcomes(idx, a=0.75, take=4.0, hold=72, pa=1.0, pf=1/3, pa2=0.0, pf2=0.0, lock_at=0.0, lock_to=0.0, deep=0.0):
    R = np.full(len(d), np.nan); K = np.zeros(len(d), np.int64); KD = np.full(len(d), -1)
    sym, j, side, lv, datr, pen = d.sym.values, d.j.values, d.side.values, d.lv.values, d.datr.values, d.pen.values
    for i in idx:
        dp = deep * float(datr[i])
        if deep > 0 and pen[i] < 0.1 + dp: continue
        O, H, L, C = E.bars(sym[i]); fill = float(lv[i]) * (1 - int(side[i]) * dp / 100)
        R[i], K[i] = simp(O, H, L, C, int(j[i]), int(side[i]), fill, float(datr[i]), a, take, hold, pa, pf, pa2, pf2, lock_at, lock_to)
    return R, K, KD
side, tf, e200 = d.side.values, d.tf_s.values, d.s_d_ema200.values
bema = pd.read_parquet(f"{E.D}/er_all.parquet", columns=["s_b_ema50"]).s_b_ema50.values
V = [("сейчас (v661)", {}, {}), ("стоп 0.6 дн. ATR", dict(a=0.6), {}), ("стоп 1.0 дн. ATR", dict(a=1.0), {}),
     ("тейк 5R", dict(take=5.0), {}), ("тейк 6R", dict(take=6.0), {}), ("держать 48ч", dict(hold=48), {}), ("держать 120ч", dict(hold=120), {}),
     ("тейк 6R, 120ч", dict(take=6.0, hold=120), {}),
     ("ещё 1/3 на +2R", dict(pa2=2.0, pf2=1/3), {}), ("ещё 1/3 на +2.5R", dict(pa2=2.5, pf2=1/3), {}),
     ("после +2R стоп на +1R", dict(lock_at=2.0, lock_to=1.0), {}), ("после +3R стоп на +1.5R", dict(lock_at=3.0, lock_to=1.5), {}),
     ("лимитка глубже на 0.1 дн. ATR", dict(deep=0.1), {}), ("лимитка глубже на 0.2 дн. ATR", dict(deep=0.2), {}),
     ("EMA200 < 6 дн. ATR", {}, dict(e2=6)), ("EMA200 < 8", {}, dict(e2=8)), ("EMA200 < 14", {}, dict(e2=14)),
     ("4ч без запаса", {}, dict(m4=0.0)), ("4ч запас +0.2", {}, dict(m4=0.2)), ("все ТФ запас +0.05", {}, dict(mall=0.05)),
     ("без фильтра BTC EMA50", {}, dict(nob=True)), ("лимит 6 сделок", {}, dict(cap=6)), ("лимит 20 сделок", {}, dict(cap=20))]
for q in (0.97, 0.90):
    target = 0.45 if q >= 0.97 else 0.50
    grid = tuple(np.round(np.arange(0.0025, 0.1, 0.0025), 4)) if q >= 0.97 else tuple(np.round(np.arange(0.001, 0.03, 0.001), 4))
    thr = np.array([E.THR[y][q] if y in E.THR else np.inf for y in E.YR]); rel = E.SC - thr
    print(f"\n=== EMA q{q}", flush=True)
    for nm, kw, fk in V:
        m = (side > 0) & (e200 < fk.get("e2", 10)) & ((tf != "4h") | (rel >= fk.get("m4", 0.1))) & (rel >= fk.get("mall", 0.0))
        if not fk.get("nob"): m &= bema > 0
        idx = E.cand(q, m)
        R, K, KD = outcomes(idx, **kw); tr = E.replay(idx, R, K, cap=fk.get("cap", 12))
        r = R[tr]; E.line(f"{nm} (минусов {np.mean(r < 0)*100:.0f}%)", tr, R, K, KD, target, grid)
