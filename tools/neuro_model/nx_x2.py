"""🧠 Neuro, night round 2 on the v0.99.663 rule (ADX < 30, BTC 1h not against, the limit 0.3 ATR / 3 h, stop 1 ATR, take 3R,
12 h, cap 12): stop / take / hold with the limit, a break-even move, the cap, the score margin, single-feature filters"""
import sys
GRP = sys.argv[1] if len(sys.argv) > 1 else "rule"
import sys, numpy as np
from numba import njit
import nx_h as N
F = N.F
@njit(cache=True)
def sim(O, H, L, C, i, s, a, lim, w, stop_k, take, hold, be_r):
    n = len(C); i0 = i + 1; e = O[i + 1]
    if lim > 0:
        lv = O[i + 1] - s * lim * a; f = -1
        for q in range(w):
            b = i + 1 + q
            if b >= n: break
            if (s > 0 and L[b] <= lv) or (s < 0 and H[b] >= lv): f = b; break
        if f < 0: return np.nan, 0
        i0 = f; e = min(lv, O[f]) if s > 0 else max(lv, O[f])
    risk = stop_k * a; st = e - s * risk; tp = e + s * take * risk; bed = False
    W = min(hold, n - i0); k = W - 1; ex = C[i0 + k]
    for q in range(W):
        b = i0 + q
        if (s > 0 and L[b] <= st) or (s < 0 and H[b] >= st):
            gap = q > 0 and ((s > 0 and O[b] <= st) or (s < 0 and O[b] >= st)); ex = O[b] if gap else st; k = q; break
        if (s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp): ex = tp; k = q; break
        if be_r > 0 and not bed and s * ((H[b] if s > 0 else L[b]) - e) >= be_r * risk: bed = True; st = e
    return (s * (ex - e) - (0.001 + 0.0003 * (k + 1) / 24) * e) / risk, k + 1 + (i0 - i - 1)
def build(q, lim=0.3, w=3, stop_k=1.0, take=3.0, hold=12, be_r=0.0, cap=12, adx=30, filt=None, margin=None):
    ev = []
    for s in (1, -1):
        m = (F["adx"] < adx) & (s * F["b_r1"] > -1)
        if filt is not None: m &= filt(s)
        rows = N.cand(s, q, m); sc = N.S[f"sc{s}"][rows]
        if margin is not None:
            thr = N.S[(f"t995_{s}" if q == 0.995 else f"t98_{s}")][rows]; k_ = sc >= thr + margin; rows, sc = rows[k_], sc[k_]
        for n_, r in enumerate(rows):
            O, H, L, C, atr = N.bars(int(N.SY[r])); i = int(N.I[r])
            if i + 20 >= len(C) or atr[i] != atr[i]: continue
            R, K = sim(O, H, L, C, i, s, float(atr[i]), lim, w, stop_k, take, hold, be_r)
            if R == R: ev.append((int(N.T[r]), -float(sc[n_]), int(N.SY[r]), s, float(R), int(K), int(r)))
    ev.sort(); busy, act, out = {}, [], []
    for t, _, sy, s, r, k, row in ev:
        if busy.get((sy, s), 0) > t: continue
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == s) >= cap: continue
        end = t + 3600 * (k + 1); busy[(sy, s)] = end; act.append((end, s)); out.append((t, end, r, s, row))
    return out
if __name__ == "__main__":
    grp = GRP
    if grp == "rule":
        V = [("сейчас (v663)", {}), ("лимитка 0.4 ATR", dict(lim=0.4)), ("ждать 2ч", dict(w=2)), ("ждать 5ч", dict(w=5)),
             ("стоп 0.75 ATR", dict(stop_k=0.75)), ("стоп 1.25 ATR", dict(stop_k=1.25)), ("стоп 1.5 ATR", dict(stop_k=1.5)),
             ("тейк 2R", dict(take=2.0)), ("тейк 2.5R", dict(take=2.5)), ("тейк 4R", dict(take=4.0)),
             ("держать 8ч", dict(hold=8)), ("держать 16ч", dict(hold=16)),
             ("б/у на +1R", dict(be_r=1.0)), ("б/у на +1.5R", dict(be_r=1.5)),
             ("лимит 6 на сторону", dict(cap=6)), ("лимит 20 на сторону", dict(cap=20)),
             ("ADX < 25", dict(adx=25)), ("ADX < 35", dict(adx=35))]
    else:
        V = [("сейчас (v663)", {}),
             ("BTC 24ч не против (>-2%)", dict(filt=lambda s: s * F["b_r24"] > -2)),
             ("BTC 24ч по направлению", dict(filt=lambda s: s * F["b_r24"] > 0)),
             ("BTC EMA50 по направлению", dict(filt=lambda s: s * F["b_e50"] > 0)),
             ("день EMA200 по направлению", dict(filt=lambda s: s * F["dd_e200"] > 0)),
             ("день EMA200 против (контртренд)", dict(filt=lambda s: s * F["dd_e200"] < 0)),
             ("объём z < 2", dict(filt=lambda s: F["vol_z"] < 2)), ("объём z > 0", dict(filt=lambda s: F["vol_z"] > 0)),
             ("ATR% < медианы", dict(filt=lambda s: F["atr_pct"] < np.nanmedian(F["atr_pct"]))),
             ("ATR% > медианы", dict(filt=lambda s: F["atr_pct"] > np.nanmedian(F["atr_pct"]))),
             ("фандинг не против", dict(filt=lambda s: s * F["fund"] <= 0)),
             ("RSI не перегрет", dict(filt=lambda s: np.where(s > 0, F["rsi14"] < 70, F["rsi14"] > 30))),
             ("24ч монеты против входа (откат)", dict(filt=lambda s: s * F["roc24"] < 0)),
             ("24ч монеты по входу", dict(filt=lambda s: s * F["roc24"] > 0))]
    for q in (0.995, 0.98):
        print(f"\n=== Нейро q{q}", flush=True)
        for nm, kw in V: N.line(nm, sorted(build(q, **kw)), q)
