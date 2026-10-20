"""Neuro night round: partial takes, holds, caps on the deployed rule (ADX < 30, BTC 1h not > 1% against; stop 1 ATR,
take 3R, 24 h; top 0.5% per side) — q 0.995 the bot, q 0.98 the check set"""
import numpy as np
from numba import njit
import nx_h as N
F = N.F
@njit(cache=True)
def simp(O, H, L, C, i, s, a, stop_k, take, hold, pa, pf):
    n = len(C); e = O[i + 1]; risk = stop_k * a; st = e - s * risk; tp = e + s * take * risk; pt = e + s * pa * risk; took = False
    W = min(hold, n - i - 1); k = W - 1; ex = C[i + k + 1] if i + k + 1 < n else C[n - 1]
    for q in range(W):
        b = i + 1 + q
        if (s > 0 and L[b] <= st) or (s < 0 and H[b] >= st):
            gap = q > 0 and ((s > 0 and O[b] <= st) or (s < 0 and O[b] >= st))
            ex = O[b] if gap else st; k = q; break
        if pa > 0 and not took and ((s > 0 and H[b] >= pt) or (s < 0 and L[b] <= pt)):
            took = True; st = e
        if (s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp):
            ex = tp; k = q; break
    fee = (0.001 + 0.0003 * (k + 1) / 24) * e / risk
    rest = s * (ex - e) / risk
    return ((pf * pa + (1 - pf) * rest) if took else rest) - fee, k + 1
def build(q, sides=(1, -1), stop_k=1.0, take=3.0, hold=24, pa=0.0, pf=0.33, cap=12):
    ev = []
    for s in sides:
        mask = (F["adx"] < 30) & (s * F["b_r1"] > -1)
        rows = N.cand(s, q, mask)
        sc = N.S[f"sc{s}"][rows]
        for n_, r in enumerate(rows):
            O, H, L, C, atr = N.bars(int(N.SY[r])); i = int(N.I[r])
            if i + 2 >= len(C) or atr[i] != atr[i]: continue
            R, K = simp(O, H, L, C, i, s, float(atr[i]), stop_k, take, hold, pa, pf)
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
        for nm, kw in (("сейчас (стоп 1 ATR, 3R, 24ч)", {}), ("1/3 на +1R → б/у", dict(pa=1.0)), ("1/2 на +1R → б/у", dict(pa=1.0, pf=0.5)),
                       ("1/3 на +0.7R → б/у", dict(pa=0.7)), ("тейк 2R", dict(take=2.0)), ("тейк 1.5R", dict(take=1.5)), ("держать 12ч", dict(hold=12)),
                       ("держать 48ч", dict(hold=48)), ("стоп 1.5 ATR, 2R", dict(stop_k=1.5, take=2.0)), ("не больше 4", dict(cap=4)), ("не больше 6", dict(cap=6))):
            tr = build(q, **kw); r = np.array([x[2] for x in tr])
            N.line(f"{nm} (минусов {np.mean(r < 0)*100:.0f}%)", sorted(tr), q)
