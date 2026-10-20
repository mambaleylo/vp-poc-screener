"""📈 round 2 on top of the stop 2 ATR: a retest entry, the exit channel length, tightening after +X R, dead-trade
exits, the EMA200 slope, one signal per coin across the two charts."""
import sys, numpy as np
from numba import njit
ARGS = sys.argv[1:]
from common import V, load
import nx_feat
import rb_h as B
from ev_engine import ema
CACHE = {}
NEX = (10, 15, 20, 30)
def bars(sym, tfh):
    k = (sym, tfh)
    if k not in CACHE:
        cs = V._oc_agg(load(sym), tfh)
        O = np.array([c["open"] for c in cs]); H = np.array([c["high"] for c in cs]); L = np.array([c["low"] for c in cs]); C = np.array([c["close"] for c in cs])
        T = np.array([c["time"] + tfh * 3600 for c in cs])
        atr = np.array([v if v is not None else np.nan for v in nx_feat._wilder(list(nx_feat._tr(list(H), list(L), list(C))), 14)])
        LO = np.stack([np.array([L[b - n:b].min() if b >= n else np.nan for b in range(len(L))]) for n in NEX])
        HI = np.stack([np.array([H[b - n:b].max() if b >= n else np.nan for b in range(len(H))]) for n in NEX])
        e200 = np.array(ema(C, 200))
        CACHE[k] = (O, H, L, C, T, atr, LO, HI, e200)
    return CACHE[k]
@njit(cache=True)
def sim(O, H, L, C, LO, HI, i0, e, s, a, stop_k, hold, tfh, ne, tight_r, ne2, dead, half):
    """from bar i0 (entered at e): the stop on touch, the ne-th channel close exit (tightened to ne2 after +tight_r R),
    dead: out at the close after `dead` bars if never +1R; half: half off at +half R, the stop to the entry."""
    n = len(C); risk = stop_k * a; hs = e - s * risk
    tight = False; best = 0.0; took = False
    k = min(hold, n - i0) - 1; ex = C[i0 + k]
    for q in range(min(hold, n - i0)):
        b = i0 + q
        if (s > 0 and L[b] <= hs) or (s < 0 and H[b] >= hs):
            ex = hs if q == 0 or not ((s > 0 and O[b] <= hs) or (s < 0 and O[b] >= hs)) else O[b]; k = q; break
        fav = (H[b] - e) / risk if s > 0 else (e - L[b]) / risk
        if fav > best: best = fav
        if half > 0 and not took and best >= half:
            took = True; hs = e
        if tight_r > 0 and best >= tight_r: tight = True
        ch = ne2 if tight else ne
        lv = LO[ch, b] if s > 0 else HI[ch, b]
        if (s > 0 and C[b] < lv) or (s < 0 and C[b] > lv):
            ex = C[b]; k = q; break
        if dead > 0 and q + 1 == dead and best < 1.0:
            ex = C[b]; k = q; break
    rest = (s * (ex - e) - 0.001 * e - 0.0003 * e * (k + 1) * tfh / 24) / risk
    if took:
        return 0.5 * half + 0.5 * rest, k + 1, ex
    return rest, k + 1, ex
def outcomes(mask, stop_k=2.0, ne=20, tight_r=0.0, ne2=10, dead=0, retest=0, half=0.0):
    R = np.full(len(B.T), np.nan); Hh = np.ones(len(B.T), np.int64); TT = B.T.copy(); EX = np.full(len(B.T), np.nan)
    outcomes.EX = EX
    for i in np.where(mask & (B.T >= B.START))[0]:
        tfh = int(B.TF[i]); O, H, L, C, T, atr, LO, HI, e200 = bars(B.SYM[i], tfh)
        j = int(np.searchsorted(T, B.T[i]))
        if j >= len(T) - 2 or T[j] != B.T[i] or atr[j] != atr[j]: continue
        s = int(B.SD[i]); hold = 180 if tfh == 24 else 360
        if retest:
            N0 = int(B.N[i]); lvl = H[j - N0:j].max() if s > 0 else L[j - N0:j].min()
            q0 = -1
            for q in range(1, retest + 1):
                if j + q >= len(C): break
                if (s > 0 and L[j + q] <= lvl) or (s < 0 and H[j + q] >= lvl): q0 = q; break
            if q0 < 0: continue
            e = min(O[j + q0], lvl) if s > 0 else max(O[j + q0], lvl)
            i0 = j + q0
        else:
            e = O[j + 1]; i0 = j + 1
        r, k, ex = sim(O, H, L, C, LO, HI, i0, e, s, float(atr[j]), stop_k, hold, tfh, NEX.index(ne), tight_r, NEX.index(ne2), dead, half)
        R[i], Hh[i] = r, k + (i0 - j - 1); EX[i] = ex
    return R, Hh
if __name__ == "__main__":
    which = ARGS[0]
    M = B.BOT if which == "bot" else B.CHECK
    print(f"== {which} (всё со стопом 2 ATR)")
    O_ = {}
    def run(nm, mask=None, **kw):
        R, H = outcomes(M if mask is None else (M & mask), **kw); tr = B.replay(M if mask is None else (M & mask), R, H); B.line(nm, tr, R, H)
    run("сейчас: стоп 2, канал 20")
    for ne in (15, 30): run(f"выход по каналу {ne}", ne=ne)
    for tr_, n2 in ((3.0, 10), (5.0, 10), (5.0, 15)): run(f"после +{tr_}R канал {n2}", tight_r=tr_, ne2=n2)
    for dd in (5, 10, 20): run(f"закрыть, если за {dd} свечей не было +1R", dead=dd)
    for rt in (3, 6): run(f"вход на ретесте границы (ждать {rt} свечей)", retest=rt)
    run("ретест 6 + половина на +2R", retest=6, half=2.0)
    run("половина на +2R", half=2.0)
    # the EMA200 slope over 10 bars in the trade's direction
    slope = np.zeros(len(B.T), bool)
    for i in np.where(M & (B.T >= B.START))[0]:
        O, H, L, C, T, atr, LO, HI, e200 = bars(B.SYM[i], int(B.TF[i])); j = int(np.searchsorted(T, B.T[i]))
        if j < len(T) and T[j] == B.T[i] and j >= 10: slope[i] = B.SD[i] * (e200[j] - e200[j - 10]) > 0
    run("EMA200 растёт в сторону сделки (10 свечей)", slope)
    # one signal per coin & side across the charts: a 12h signal skipped when the same coin & side had a day signal within 2 days
    day = {}
    for i in np.where(M & (B.TF == 24))[0]: day.setdefault((B.SYM[i], B.SD[i]), []).append(B.T[i])
    dup = np.zeros(len(B.T), bool)
    for i in np.where(M & (B.TF == 12))[0]:
        dup[i] = any(abs(t - B.T[i]) <= 2 * 86400 for t in day.get((B.SYM[i], B.SD[i]), []))
    run("12ч без дублей дневного сигнала", ~dup)
