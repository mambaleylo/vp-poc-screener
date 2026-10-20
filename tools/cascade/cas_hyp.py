"""EMA cascade hypotheses on the saved walk-forward scores: exits (take, hold, break-even, trailing by the cascade,
stop by close) and filters (BTC, ADX, hour, the cross's context). Judged at equal pain on the bot's set (q 0.995)
and a check set (q 0.98)."""
import os, sys, numpy as np, datetime as dt
ARGS = sys.argv[1:]
from numba import njit
from cas_h import S, SD, T, SY, X, YR, bars, line, ts
import nx_feat
NI = {n: 9 + k for k, n in enumerate(nx_feat.NAMES)}
CI = {n: 1 + k for k, n in enumerate(["rng", "prior", "since_opp", "exc", "move24", "width", "b24", "atrp"])}
F = lambda n: X[:, NI[n]] if n in NI else X[:, CI[n]]
@njit(cache=True)
def sim(O, H, L, C, TOP, BOT, i, s, a, stop_k, take_r, hold, be_r, trail_r, close_stop, hard_k):
    n = len(C); e = O[i + 1]
    if stop_k > 0: stop = e - s * stop_k * a
    else:
        lo = L[i]; hi = H[i]
        for k in range(max(0, i - 23), i + 1):
            lo = min(lo, L[k]); hi = max(hi, H[k])
        stop = (lo - 0.2 * a) if s > 0 else (hi + 0.2 * a)
    risk = s * (e - stop)
    if risk <= e * 0.002: return np.nan, 0, 0
    hs = e - s * hard_k * risk if close_stop else stop
    R = risk * hard_k if close_stop else risk      # R per the sizing risk (the hard stop)
    W = min(hold, n - i - 2)
    if W < hold: return np.nan, 0, 0
    tp = e + s * take_r * risk; best = 0.0; st = stop; k = W - 1; px = C[i + 1 + k]; kind = 2
    for q in range(W):
        b = i + 1 + q
        hit = (L[b] <= hs) if s > 0 else (H[b] >= hs)
        if not close_stop or st != stop: hit = hit or ((L[b] <= st) if s > 0 else (H[b] >= st))
        if hit:
            lvl = hs if (close_stop and st == stop) else st
            if close_stop and st == stop: lvl = hs
            gap = q > 0 and ((O[b] <= lvl) if s > 0 else (O[b] >= lvl))
            px = O[b] if gap else lvl; k = q; kind = 0; break
        if take_r > 0 and ((H[b] >= tp) if s > 0 else (L[b] <= tp)):
            px = tp; k = q; kind = 1; break
        if close_stop and st == stop and ((C[b] <= stop) if s > 0 else (C[b] >= stop)):
            px = C[b]; k = q; kind = 0; break
        best = max(best, ((H[b] - e) if s > 0 else (e - L[b])) / risk)
        if be_r > 0 and best >= be_r and s * (st - e) < 0: st = e
        if trail_r >= 0 and best >= trail_r and ((C[b] < BOT[b]) if s > 0 else (C[b] > TOP[b])):
            px = C[b]; k = q; kind = 3; break
    return (s * (px - e) - (0.001 + 0.0003 * (k + 1) / 24) * e) / R, k + 1, kind
def trades(q, mask=None, nm="sw_t2_48", stop_k=-1.0, take_r=2.0, hold=48, be_r=0.0, trail_r=-1.0, close_stop=False, hard_k=2.0, cap=12, sides=(1, -1)):
    ev = []
    for s in sides:
        sc = S[f"sc_{nm}_{s}"]
        if f"thrv_{nm}_{s}_{q}" in S.files: tv = S[f"thrv_{nm}_{s}_{q}"]
        else:
            thr = np.array([S[f"thr_{nm}_{s}_{q}_{y}"] if f"thr_{nm}_{s}_{q}_{y}" in S.files else np.inf for y in range(2000, 2030)])
            tv = thr[np.clip(YR - 2000, 0, 29)]
        m = (SD == s) & ~np.isnan(sc) & (sc >= tv)
        if mask is not None: m &= mask
        for r in np.where(m)[0]: ev.append((int(T[r]), -float(sc[r]), int(SY[r]), s, int(r)))
    ev.sort(); busy, act, out = {}, [], []
    for t, _, sy, s, r in ev:
        if busy.get((sy, s), 0) > t: continue
        act = [x for x in act if x[0] > t]
        if sum(1 for x in act if x[1] == s) >= cap: continue
        O, H, L, C, TOP, BOT, atr, tm = bars(sy); i = int(np.searchsorted(tm, t))
        if i >= len(tm) or tm[i] != t: continue
        R, k, kind = sim(O, H, L, C, TOP, BOT, i, s, atr[i], stop_k, take_r, hold, be_r, trail_r, close_stop, hard_k)
        if R != R: continue
        end = t + 3600 * (k + 1); busy[(sy, s)] = end; act.append((end, s)); out.append((t, end, float(R), s, r))
    return out
def both(name, **kw):
    line(f"{name} | бот", trades(0.995, **kw), 0.995)
    line(f"{name} | проверка", trades(0.98, **kw), 0.98)
if __name__ == "__main__":
    MODE = ARGS[0] if ARGS else "exits"
    if MODE == "exits":
        both("база: свинг, тейк 2R, 48ч")
        for tk in (1.5, 2.5, 3.0, 4.0): both(f"тейк {tk}R", take_r=tk)
        for h in (24, 72, 96): both(f"держать {h}ч", hold=h)
        both("тейк 3R, 72ч", take_r=3.0, hold=72)
        for be in (1.0, 1.5): both(f"безубыток после +{be}R", be_r=be)
        for tr_ in (0.0, 1.0): both(f"без тейка, выход по каскаду после +{tr_}R, 96ч", take_r=0.0, trail_r=tr_, hold=96)
        both("тейк 4R + выход по каскаду после +1R, 96ч", take_r=4.0, trail_r=1.0, hold=96)
        for k in (1.5, 2.0): both(f"стоп по закрытию, аварийный x{k}", close_stop=True, hard_k=k)
        for sk in (1.5, 2.0, 3.0): both(f"стоп {sk} ATR вместо свинга", stop_k=sk)
    elif MODE == "filters":
        b24, b1, adx, hr = F("b_r24"), F("b_r1"), F("adx"), F("hour")
        SDs = SD.astype(float)
        both("база")
        for th in (2.0, 3.0, 4.0): both(f"BTC 24ч против сделки < {th}%", mask=(SDs * b24 > -th))
        both("BTC 1ч против сделки < 1%", mask=(SDs * b1 > -1.0))
        both("BTC 24ч по сделке", mask=(SDs * b24 > 0))
        both("BTC выше/ниже EMA50 по сделке", mask=(SDs * F("b_e50") > 0))
        for a in (25, 30, 40): both(f"ADX < {a}", mask=(adx < a))
        both("ADX > 20", mask=(adx > 20))
        both("тренд дня по сделке (EMA200)", mask=(SDs * F("dd_e200") > 0))
        both("тренд дня против сделки", mask=(SDs * F("dd_e200") < 0))
        both("отбой: обратный пробой <= 12 свечей", mask=(F("since_opp") <= 12))
        both("не отбой: обратный пробой > 12", mask=(F("since_opp") > 12))
        both("каскад узкий (< медианы)", mask=(F("width") < np.median(F("width"))))
        both("ночь UTC 0-7 убрать", mask=~((hr >= 0) & (hr < 8)))
        both("выходные убрать", mask=(F("weekend") < 0.5))
        both("фандинг по сделке (лонг при отриц.)", mask=(SDs * F("fund") <= 0))
        for cap in (4, 8, 20): both(f"не больше {cap} в сторону", cap=cap)
