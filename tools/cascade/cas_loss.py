"""🌊 cascade — fewer losing trades (the user: "избегание вообще минусовых сделок"). On the 3-model walk-forward scores
(cas_sel_base3.npz) and the deployed rule (a third at +0.7R -> the stop to the entry, take 2.5R, 48 h, 6 per side):
exits (no progress after N bars, back inside / through the cascade, earlier break-even / partial), entries
(a confirmation bar, a retest limit at the cascade), filters. Bot set q 0.995, check set q 0.98."""
import os, sys
ARGS = sys.argv[1:]
os.environ.setdefault("CAS_SEL", "cas_sel_base3.npz")
import numpy as np
from numba import njit
from cas_h import S, SD, T, SY, YR, X, bars
from wr_eval import stats
from mk import ts
import nx_feat
NI = {n: 9 + k for k, n in enumerate(nx_feat.NAMES)}
CI = {n: 1 + k for k, n in enumerate(["rng", "prior", "since_opp", "exc", "move24", "width", "b24", "atrp"])}
F = lambda n: X[:, NI[n]] if n in NI else X[:, CI[n]]
@njit(cache=True)
def sim(O, H, L, C, TOP, BOT, i, s, a, take_r, hold, part_r, part_f, be_r, nop_k, nop_r, fail_k, fail_mode, entry, ret_k):
    n = len(C)
    lo = L[i]; hi = H[i]
    for k in range(max(0, i - 23), i + 1):
        lo = min(lo, L[k]); hi = max(hi, H[k])
    stop = (lo - 0.2 * a) if s > 0 else (hi + 0.2 * a)
    i0 = i + 1; e = O[i + 1]
    if entry == 1:      # the next bar must close beyond the cascade too
        if (s > 0 and C[i + 1] <= TOP[i + 1]) or (s < 0 and C[i + 1] >= BOT[i + 1]): return np.nan, 0, 0
        i0 = i + 2; e = O[i + 2]
    elif entry == 2:    # a limit at the near cascade edge (the top EMA for a long), waiting ret_k bars
        lvl = TOP[i] if s > 0 else BOT[i]; q0 = -1
        for q in range(1, ret_k + 1):
            if i + q >= n: break
            if (s > 0 and L[i + q] <= lvl) or (s < 0 and H[i + q] >= lvl): q0 = q; break
        if q0 < 0: return np.nan, 0, 0
        i0 = i + q0; e = min(O[i0], lvl) if s > 0 else max(O[i0], lvl)
    risk = s * (e - stop)
    if risk <= e * 0.002 or i0 + hold >= n: return np.nan, 0, 0
    tp = e + s * take_r * risk; st = stop; took = False; best = 0.0; k = hold - 1; px = C[i0 + hold - 1]; kind = 3
    for q in range(hold):
        b = i0 + q
        if (L[b] <= st) if s > 0 else (H[b] >= st):
            gap = q > 0 and ((O[b] <= st) if s > 0 else (O[b] >= st))
            px = O[b] if gap else st; k = q; kind = 1 if took else 0; break
        fav = ((H[b] - e) if s > 0 else (e - L[b])) / risk
        if part_r > 0 and not took and fav >= part_r:
            took = True; st = e
        if (H[b] >= tp) if s > 0 else (L[b] <= tp):
            px = tp; k = q; kind = 2; break
        best = max(best, fav)
        if be_r > 0 and best >= be_r and s * (st - e) < 0: st = e
        if nop_k > 0 and q + 1 == nop_k and best < nop_r and not took:
            px = C[b]; k = q; kind = 4; break
        if fail_k > 0 and q < fail_k and not took:
            back = (C[b] < TOP[b]) if (s > 0 and fail_mode == 1) else ((C[b] < BOT[b]) if s > 0 else ((C[b] > BOT[b]) if fail_mode == 1 else (C[b] > TOP[b])))
            if back: px = C[b]; k = q; kind = 5; break
    fee = (0.001 + 0.0003 * (k + 1) / 24) * e / risk
    rest = s * (px - e) / risk
    return ((part_f * part_r + (1 - part_f) * rest) if took else rest) - fee, k + 1 + (i0 - i - 1), kind
def trades(q, mask=None, take_r=2.5, hold=48, part_r=0.7, part_f=0.33, be_r=0.0, nop_k=0, nop_r=0.3, fail_k=0, fail_mode=1, entry=0, ret_k=3, cap=6, sc_min=None):
    ev = []
    for s in (1, -1):
        sc = S[f"sc_sw_t2_48_{s}"]; tv = S[f"thrv_sw_t2_48_{s}_{q}"]
        m = (SD == s) & ~np.isnan(sc) & (sc >= tv)
        if sc_min is not None: m &= sc >= tv + sc_min
        if mask is not None: m &= mask
        for r in np.where(m)[0]: ev.append((int(T[r]), -float(sc[r]), int(SY[r]), s, int(r)))
    ev.sort(); busy, act, out = {}, [], []
    for t, _, sy, s, r in ev:
        if busy.get((sy, s), 0) > t: continue
        act = [x for x in act if x[0] > t]
        if sum(1 for x in act if x[1] == s) >= cap: continue
        O, H, L, C, TOP, BOT, atr, tm = bars(sy); i = int(np.searchsorted(tm, t))
        if i >= len(tm) - 3 or tm[i] != t: continue
        R, k, kind = sim(O, H, L, C, TOP, BOT, i, s, atr[i], take_r, hold, part_r, part_f, be_r, nop_k, nop_r, fail_k, fail_mode, entry, ret_k)
        if R != R: continue
        end = t + 3600 * k; busy[(sy, s)] = end; act.append((end, s)); out.append((t, end, float(R), s, r, kind))
    return out
def show(nm, kw, sets=((0.995, 0.45, "бот"), (0.98, 0.50, "пров"))):
    for q, tg, sn in sets:
        tr = [x for x in trades(q, **kw) if x[0] >= ts(2022)]
        r = np.array([x[2] for x in tr])
        lo = f"минусов {np.mean(r < 0)*100:2.0f}% (ср. {r[r < 0].mean():+.2f}R)" if len(r) else ""
        stats(f"{nm[:34]:34s} {sn} {lo}", [x[:5] for x in tr], ts(2022), tg)
if __name__ == "__main__":
    MODE = ARGS[0] if ARGS else "exits"
    if MODE == "exits":
        V = [("сейчас", {}),
             ("нет +0.3R за 6 свечей — выход", dict(nop_k=6)), ("нет +0.3R за 12 — выход", dict(nop_k=12)), ("нет +0.5R за 12 — выход", dict(nop_k=12, nop_r=0.5)),
             ("нет +0.3R за 24 — выход", dict(nop_k=24)),
             ("назад в каскад (за верх. EMA), 3 свечи", dict(fail_k=3, fail_mode=1)), ("назад в каскад, 6 свечей", dict(fail_k=6, fail_mode=1)),
             ("сквозь каскад обратно, 6 свечей", dict(fail_k=6, fail_mode=2)), ("сквозь каскад, 12", dict(fail_k=12, fail_mode=2)),
             ("частичная 1/3 на +0.5R", dict(part_r=0.5)), ("частичная 1/2 на +0.5R", dict(part_r=0.5, part_f=0.5)),
             ("б/у на +0.5R (без частичной)", dict(part_r=0.0, be_r=0.5)),
             ("вход: подтверждение след. свечой", dict(entry=1)), ("вход: лимитка на ретест каскада (3)", dict(entry=2, ret_k=3)),
             ("вход: ретест (6)", dict(entry=2, ret_k=6))]
        for nm, kw in V: show(nm, kw)
    elif MODE == "filters":
        SDf = SD.astype(float)
        V = [("сейчас", None), ("BTC 24ч против < 2%", SDf * F("b_r24") > -2), ("BTC 1ч против < 0.5%", SDf * F("b_r1") > -0.5),
             ("BTC 24ч по сделке", SDf * F("b_r24") > 0), ("BTC EMA50 по сделке", SDf * F("b_e50") > 0),
             ("ADX < 30", F("adx") < 30), ("ADX > 20", F("adx") > 20), ("тренд дня по сделке", SDf * F("dd_e200") > 0), ("тренд дня против", SDf * F("dd_e200") < 0),
             ("RSI не перегрет (л<70/ш>30)", np.where(SD > 0, F("rsi14") < 70, F("rsi14") > 30)), ("объём выше нормы (vol_z>0)", F("vol_z") > 0),
             ("каскад узкий", F("width") < np.nanmedian(F("width"))), ("отбой (обр. пробой ≤12)", F("since_opp") <= 12),
             ("не ночь UTC 0-6", ~((F("hour") >= 0) & (F("hour") < 7))), ("фандинг не против", SDf * F("fund") <= 0)]
        for nm, m in V: show(nm, {"mask": m})
        for cap in (2, 3, 4): show(f"не больше {cap} в сторону", {"cap": cap})
        for dm in (0.02, 0.05, 0.1): show(f"оценка выше порога на {dm}", {"sc_min": dm})
