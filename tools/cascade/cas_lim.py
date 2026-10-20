"""🌊 cascade: the entry by a limit x ATR better than the next open (waiting w bars) on the deployed rule"""
import os
os.environ.setdefault("CAS_SEL", "cas_sel_base3.npz")
import numpy as np
from numba import njit
from cas_h import S, SD, T, SY, bars
from wr_eval import stats
from mk import ts
@njit(cache=True)
def sim(O, H, L, C, i, s, a, lim, w, take_r=2.5, hold=48, pr=0.7, pf=0.33):
    n = len(C)
    lo = L[i]; hi = H[i]
    for k in range(max(0, i - 23), i + 1):
        lo = min(lo, L[k]); hi = max(hi, H[k])
    stop = (lo - 0.2 * a) if s > 0 else (hi + 0.2 * a)
    i0 = i + 1; e = O[i + 1]
    if lim > 0:
        lv = O[i + 1] - s * lim * a; f = -1
        for q in range(w):
            b = i + 1 + q
            if b >= n: break
            if (s > 0 and L[b] <= lv) or (s < 0 and H[b] >= lv): f = b; break
        if f < 0: return np.nan, 0
        i0 = f; e = min(lv, O[f]) if s > 0 else max(lv, O[f])
    risk = s * (e - stop)
    if risk <= e * 0.002 or i0 + hold >= n: return np.nan, 0
    tp = e + s * take_r * risk; st = stop; took = False; k = hold - 1; px = C[i0 + hold - 1]
    for q in range(hold):
        b = i0 + q
        if (s > 0 and L[b] <= st) or (s < 0 and H[b] >= st):
            gap = q > 0 and ((s > 0 and O[b] <= st) or (s < 0 and O[b] >= st))
            px = O[b] if gap else st; k = q; break
        if not took and ((H[b] - e) if s > 0 else (e - L[b])) >= pr * risk:
            took = True; st = e
        if (s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp):
            px = tp; k = q; break
    fee = (0.001 + 0.0003 * (k + 1) / 24) * e / risk
    rest = s * (px - e) / risk
    return ((pf * pr + (1 - pf) * rest) if took else rest) - fee, k + 1 + (i0 - i - 1)
def trades(q, lim=0.0, w=3, cap=6):
    ev = []
    for s in (1, -1):
        sc = S[f"sc_sw_t2_48_{s}"]; tv = S[f"thrv_sw_t2_48_{s}_{q}"]
        for r in np.where((SD == s) & ~np.isnan(sc) & (sc >= tv))[0]: ev.append((int(T[r]), -float(sc[r]), int(SY[r]), s, int(r)))
    ev.sort(); busy, act, out = {}, [], []
    for t, _, sy, s, r in ev:
        if busy.get((sy, s), 0) > t: continue
        act = [x for x in act if x[0] > t]
        if sum(1 for x in act if x[1] == s) >= cap: continue
        O, H, L, C, TOP, BOT, atr, tm = bars(sy); i = int(np.searchsorted(tm, t))
        if i >= len(tm) - 3 or tm[i] != t: continue
        R, k = sim(O, H, L, C, i, s, atr[i], lim, w)
        if R != R: continue
        end = t + 3600 * k; busy[(sy, s)] = end; act.append((end, s)); out.append((t, end, float(R), s, r))
    return out
for q, tg in ((0.995, 0.45), (0.98, 0.50)):
    print(f"\n=== каскад q{q}")
    for nm, lim, w in (("сейчас (по рынку)", 0, 0), ("лимитка −0.2 ATR, 3ч", 0.2, 3), ("лимитка −0.3 ATR, 3ч", 0.3, 3), ("лимитка −0.5 ATR, 3ч", 0.5, 3), ("лимитка −0.3 ATR, 6ч", 0.3, 6)):
        tr = trades(q, lim, w); r = np.array([x[2] for x in tr if x[0] >= ts(2022)])
        stats(f"{nm} ({r.mean():+.3f}R)", tr, ts(2022), tg)
