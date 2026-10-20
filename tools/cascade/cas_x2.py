"""🌊 cascade, night round 2 on the v0.99.653 rule (the swing stop 24 bars ± 0.2 ATR, 1/3 off at +0.7R → break-even, take 2.5R,
48 h, cap 6): the swing length / buffer, the stop width as an entry filter, the hold, the rest trailing behind the
cascade instead of the take, a later take, a cool-down after a loss on the coin"""
import os, sys
os.environ.setdefault("CAS_SEL", "cas_sel_base3.npz")
import numpy as np
from numba import njit
from cas_h import S, SD, T, SY, bars
from wr_eval import stats
from mk import ts
@njit(cache=True)
def sim(O, H, L, C, TOP, BOT, i, s, a, sw, buf, take_r, hold, pr, pf, trail):
    n = len(C)
    lo = L[i]; hi = H[i]
    for k in range(max(0, i - sw + 1), i + 1):
        lo = min(lo, L[k]); hi = max(hi, H[k])
    stop = (lo - buf * a) if s > 0 else (hi + buf * a)
    i0 = i + 1; e = O[i + 1]
    risk = s * (e - stop)
    if risk <= e * 0.002 or i0 + hold >= n: return np.nan, 0, 0.0
    tp = e + s * take_r * risk; st = stop; took = False; k = hold - 1; px = C[i0 + hold - 1]
    for q in range(hold):
        b = i0 + q
        if (s > 0 and L[b] <= st) or (s < 0 and H[b] >= st):
            gap = q > 0 and ((s > 0 and O[b] <= st) or (s < 0 and O[b] >= st))
            px = O[b] if gap else st; k = q; break
        if not took and ((H[b] - e) if s > 0 else (e - L[b])) >= pr * risk:
            took = True; st = e
        if take_r > 0 and ((s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp)):
            px = tp; k = q; break
        if trail and took and ((s > 0 and C[b] < BOT[b]) or (s < 0 and C[b] > TOP[b])):
            px = C[b]; k = q; break
    fee = (0.001 + 0.0003 * (k + 1) / 24) * e / risk
    rest = s * (px - e) / risk
    return ((pf * pr + (1 - pf) * rest) if took else rest) - fee, k + 1, risk / a
def trades(q, sw=24, buf=0.2, take_r=2.5, hold=48, pr=0.7, pf=0.33, trail=False, cap=6, rmin=0.0, rmax=99.0, cool=0):
    ev = []
    for s in (1, -1):
        sc = S[f"sc_sw_t2_48_{s}"]; tv = S[f"thrv_sw_t2_48_{s}_{q}"]
        for r in np.where((SD == s) & ~np.isnan(sc) & (sc >= tv))[0]: ev.append((int(T[r]), -float(sc[r]), int(SY[r]), s, int(r)))
    ev.sort(); busy, act, out, lost = {}, [], [], {}
    for t, _, sy, s, r in ev:
        if busy.get((sy, s), 0) > t: continue
        if cool and lost.get((sy, s), -1e18) + cool * 3600 > t: continue
        act = [x for x in act if x[0] > t]
        if sum(1 for x in act if x[1] == s) >= cap: continue
        O, H, L, C, TOP, BOT, atr, tm = bars(sy); i = int(np.searchsorted(tm, t))
        if i >= len(tm) - 3 or tm[i] != t: continue
        R, k, rw = sim(O, H, L, C, TOP, BOT, i, s, atr[i], sw, buf, take_r, hold, pr, pf, trail)
        if R != R or rw < rmin or rw > rmax: continue
        end = t + 3600 * k; busy[(sy, s)] = end; act.append((end, s)); out.append((t, end, float(R), s, r))
        if R < 0: lost[(sy, s)] = end
    return out
V = [("сейчас", {}), ("свинг 12 свечей", dict(sw=12)), ("свинг 36 свечей", dict(sw=36)), ("свинг 48 свечей", dict(sw=48)),
     ("запас 0.1 ATR", dict(buf=0.1)), ("запас 0.5 ATR", dict(buf=0.5)),
     ("стоп ≥ 1 ATR (узкие не брать)", dict(rmin=1.0)), ("стоп ≥ 1.5 ATR", dict(rmin=1.5)), ("стоп ≤ 4 ATR (широкие не брать)", dict(rmax=4.0)),
     ("стоп ≤ 3 ATR", dict(rmax=3.0)), ("стоп 1.5–5 ATR", dict(rmin=1.5, rmax=5.0)),
     ("держать 24ч", dict(hold=24)), ("держать 72ч", dict(hold=72)),
     ("тейк 3R", dict(take_r=3.0)), ("тейк 4R", dict(take_r=4.0)),
     ("остаток — пока за каскадом (без тейка)", dict(take_r=0.0, trail=True, hold=96)),
     ("тейк 4R + выход за каскад", dict(take_r=4.0, trail=True, hold=72)),
     ("пауза 24ч после минуса по монете", dict(cool=24)), ("пауза 72ч после минуса", dict(cool=72))]
for q, tg in ((0.995, 0.45), (0.98, 0.50)):
    print(f"\n=== каскад q{q}", flush=True)
    for nm, kw in V:
        tr = trades(q, **kw); r = np.array([x[2] for x in tr if x[0] >= ts(2022)])
        stats(f"{nm} ({r.mean():+.3f}R)", tr, ts(2022), tg)
