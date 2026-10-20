"""Neuro: the entry by a limit x ATR better than the next open (3 bars) on the deployed rule (now 12 h)"""
import numpy as np
from numba import njit
import nx_h as N
F = N.F
@njit(cache=True)
def sim(O, H, L, C, i, s, a, lim, w, stop_k=1.0, take=3.0, hold=12):
    n = len(C); i0 = i + 1; e = O[i + 1]
    if lim > 0:
        lv = O[i + 1] - s * lim * a; f = -1
        for q in range(w):
            b = i + 1 + q
            if b >= n: break
            if (s > 0 and L[b] <= lv) or (s < 0 and H[b] >= lv): f = b; break
        if f < 0: return np.nan, 0
        i0 = f; e = min(lv, O[f]) if s > 0 else max(lv, O[f])
    risk = stop_k * a; st = e - s * risk; tp = e + s * take * risk
    W = min(hold, n - i0); k = W - 1; ex = C[i0 + k]
    for q in range(W):
        b = i0 + q
        if (s > 0 and L[b] <= st) or (s < 0 and H[b] >= st):
            gap = q > 0 and ((s > 0 and O[b] <= st) or (s < 0 and O[b] >= st)); ex = O[b] if gap else st; k = q; break
        if (s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp): ex = tp; k = q; break
    return (s * (ex - e) - (0.001 + 0.0003 * (k + 1) / 24) * e) / risk, k + 1 + (i0 - i - 1)
def build(q, lim=0.0, w=3, cap=12):
    ev = []
    for s in (1, -1):
        rows = N.cand(s, q, (F["adx"] < 30) & (s * F["b_r1"] > -1)); sc = N.S[f"sc{s}"][rows]
        for n_, r in enumerate(rows):
            O, H, L, C, atr = N.bars(int(N.SY[r])); i = int(N.I[r])
            if i + 20 >= len(C) or atr[i] != atr[i]: continue
            R, K = sim(O, H, L, C, i, s, float(atr[i]), lim, w)
            if R == R: ev.append((int(N.T[r]), -float(sc[n_]), int(N.SY[r]), s, float(R), int(K), int(r)))
    ev.sort(); busy, act, out = {}, [], []
    for t, _, sy, s, r, k, row in ev:
        if busy.get((sy, s), 0) > t: continue
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == s) >= cap: continue
        end = t + 3600 * (k + 1); busy[(sy, s)] = end; act.append((end, s)); out.append((t, end, r, s, row))
    return out
if __name__ == "__main__":
    for q in (0.995, 0.98):
        print(f"\n=== Нейро q{q}")
        for nm, lim in (("сейчас (по рынку, 12ч)", 0.0), ("лимитка −0.2 ATR", 0.2), ("лимитка −0.3 ATR", 0.3), ("лимитка −0.5 ATR", 0.5)):
            N.line(nm, sorted(build(q, lim)), q)
