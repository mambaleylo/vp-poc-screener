"""🌊 cascade: win rate / losing runs — partial takes, break-even, caps, a pause after losses (bot set q 0.995)"""
import numpy as np
from numba import njit
import cas_hyp as Hh
from cas_h import S, SD, T, SY, YR, bars
from wr_eval import stats, pause
from mk import ts
@njit(cache=True)
def sim(O, H, L, C, i, s, a, take_r, hold, part_r, part_f, be_r):
    n = len(C); e = O[i + 1]
    lo = L[i]; hi = H[i]
    for k in range(max(0, i - 23), i + 1):
        lo = min(lo, L[k]); hi = max(hi, H[k])
    stop = (lo - 0.2 * a) if s > 0 else (hi + 0.2 * a)
    risk = s * (e - stop)
    if risk <= e * 0.002: return np.nan, 0
    W = min(hold, n - i - 2)
    if W < hold: return np.nan, 0
    tp = e + s * take_r * risk; st = stop; best = 0.0; took = False; k = W - 1; px = C[i + 1 + k]
    for q in range(W):
        b = i + 1 + q
        if (L[b] <= st) if s > 0 else (H[b] >= st):
            gap = q > 0 and ((O[b] <= st) if s > 0 else (O[b] >= st))
            px = O[b] if gap else st; k = q; break
        if part_r > 0 and not took and ((H[b] - e) if s > 0 else (e - L[b])) >= part_r * risk:
            took = True; st = e
        if (H[b] >= tp) if s > 0 else (L[b] <= tp):
            px = tp; k = q; break
        best = max(best, ((H[b] - e) if s > 0 else (e - L[b])) / risk)
        if be_r > 0 and best >= be_r: st = e if s * (st - e) < 0 else st
    fee = (0.001 + 0.0003 * (k + 1) / 24) * e
    rest = (s * (px - e)) / risk
    r = (part_f * part_r + (1 - part_f) * rest) if took else rest
    return r - fee / risk, k + 1
def trades(q, take_r=2.0, hold=48, part_r=0.0, part_f=0.5, be_r=0.0, cap=12):
    ev = []
    for s in (1, -1):
        sc = S[f"sc_sw_t2_48_{s}"]
        if f"thrv_sw_t2_48_{s}_{q}" in S.files: tv = S[f"thrv_sw_t2_48_{s}_{q}"]
        else:
            thr = np.array([S[f"thr_sw_t2_48_{s}_{q}_{y}"] if f"thr_sw_t2_48_{s}_{q}_{y}" in S.files else np.inf for y in range(2000, 2030)])
            tv = thr[np.clip(YR - 2000, 0, 29)]
        m = (SD == s) & ~np.isnan(sc) & (sc >= tv)
        for r in np.where(m)[0]: ev.append((int(T[r]), -float(sc[r]), int(SY[r]), s, int(r)))
    ev.sort(); busy, act, out = {}, [], []
    for t, _, sy, s, r in ev:
        if busy.get((sy, s), 0) > t: continue
        act = [x for x in act if x[0] > t]
        if sum(1 for x in act if x[1] == s) >= cap: continue
        O, H, L, C, TOP, BOT, atr, tm = bars(sy); i = int(np.searchsorted(tm, t))
        if i >= len(tm) or tm[i] != t: continue
        R, k = sim(O, H, L, C, i, s, atr[i], take_r, hold, part_r, part_f, be_r)
        if R != R: continue
        end = t + 3600 * (k + 1); busy[(sy, s)] = end; act.append((end, s)); out.append((t, end, float(R), s, r))
    return out
if __name__ == "__main__":
    F0 = ts(2022)
    V = [("сейчас: тейк 2R, до 12 в сторону", {}),
         ("тейк 2.5R, до 8", dict(take_r=2.5, cap=8)),
         ("тейк 2.5R, до 6", dict(take_r=2.5, cap=6)),
         ("тейк 2.5R, до 4", dict(take_r=2.5, cap=4)),
         ("половина на +1R → безубыток, тейк 2.5R, до 8", dict(take_r=2.5, cap=8, part_r=1.0)),
         ("половина на +1R → б/у, тейк 3R, до 8", dict(take_r=3.0, cap=8, part_r=1.0)),
         ("треть на +1R → б/у, тейк 2.5R, до 8", dict(take_r=2.5, cap=8, part_r=1.0, part_f=0.33)),
         ("половина на +0.7R → б/у, тейк 2.5R, до 8", dict(take_r=2.5, cap=8, part_r=0.7)),
         ("половина на +1.5R → б/у, тейк 3R, до 8", dict(take_r=3.0, cap=8, part_r=1.5)),
         ("безубыток после +1R, тейк 2.5R, до 8", dict(take_r=2.5, cap=8, be_r=1.0)),
         ("тейк 1.5R, до 8", dict(take_r=1.5, cap=8)),
         ("тейк 1R, до 8", dict(take_r=1.0, cap=8))]
    for q, tg in ((0.995, 0.45), (0.98, 0.50)):
        print(f"\n=== {'бот (топ 0.5%)' if q == 0.995 else 'проверка (топ 2%)'}")
        for nm, kw in V: stats(nm, trades(q, **kw), F0, tg)
        base = trades(q, take_r=2.5, cap=8)
        for L in (3, 4, 5, 6): stats(f"тейк 2.5R, до 8 + пауза после {L} минусов", pause(base, L), F0, tg)
        pb = trades(q, take_r=2.5, cap=8, part_r=1.0)
        for L in (4, 6): stats(f"половина +1R, 2.5R, до 8 + пауза после {L}", pause(pb, L), F0, tg)
