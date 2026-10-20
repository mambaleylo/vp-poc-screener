"""📈 Range breakout exits re-simulated on the chart's bars (the same bars / ATR / Donchian as bt_trades.rbx_trades):
a stop on touch or by the bar's close with a hard stop, the 20-bar Donchian close exit, optional half off at +X R."""
import sys, numpy as np
ARGS = sys.argv[1:]
from numba import njit
from common import V, load
import nx_feat
import rb_h as B
CACHE = {}
def bars(sym, tfh):
    k = (sym, tfh)
    if k not in CACHE:
        cs = V._oc_agg(load(sym), tfh)
        O = np.array([c["open"] for c in cs]); H = np.array([c["high"] for c in cs]); L = np.array([c["low"] for c in cs]); C = np.array([c["close"] for c in cs])
        T = np.array([c["time"] + tfh * 3600 for c in cs])
        atr = np.array([v if v is not None else np.nan for v in nx_feat._wilder(list(nx_feat._tr(list(H), list(L), list(C))), 14)])
        lo = np.array([L[max(0, b - 20):b].min() if b >= 20 else np.nan for b in range(len(L))]); hi = np.array([H[max(0, b - 20):b].max() if b >= 20 else np.nan for b in range(len(H))])
        CACHE[k] = (O, H, L, C, T, atr, lo, hi)
    return CACHE[k]
@njit(cache=True)
def sim(O, H, L, C, lo, hi, i, s, a, soft, hard, hold, tfh, half):
    """soft: stop in ATR (on touch when hard == 0, else on the bar's close); hard: the hard stop (intrabar);
    half: R where half the position closes and the stop goes to the entry (0 = off). R per the sizing risk (hard or soft)."""
    n = len(C); e = O[i + 1]
    risk = (hard if hard > 0 else soft) * a
    hs = e - s * risk; ss = e - s * soft * a
    took = False; r_half = 0.0; be = False
    k = min(hold, n - i - 1) - 1; ex = C[i + 1 + k]; kind = 3
    for q in range(min(hold, n - i - 1)):
        b = i + 1 + q
        if (s > 0 and L[b] <= hs) or (s < 0 and H[b] >= hs):
            ex = hs if not ((s > 0 and O[b] <= hs) or (s < 0 and O[b] >= hs)) or q == 0 else O[b]; k = q; kind = 0; break
        if half > 0 and not took and ((s > 0 and H[b] >= e + half * risk) or (s < 0 and L[b] <= e - half * risk)):
            took = True; r_half = half; hs = e; ss = e
        if hard > 0 and ((s > 0 and C[b] <= ss) or (s < 0 and C[b] >= ss)):
            ex = C[b]; k = q; kind = 1; break
        lv = lo[b] if s > 0 else hi[b]
        if (s > 0 and C[b] < lv) or (s < 0 and C[b] > lv):
            ex = C[b]; k = q; kind = 2; break
    rest = (s * (ex - e) - 0.001 * e - 0.0003 * e * (k + 1) * tfh / 24) / risk
    if took:
        return 0.5 * r_half + 0.5 * rest, k + 1, kind
    return rest, k + 1, kind
def outcomes(mask, soft=1.5, hard=0.0, half=0.0):
    R = np.full(len(B.T), np.nan); H_ = np.ones(len(B.T), np.int64)
    for i in np.where(mask & (B.T >= B.START))[0]:
        tfh = int(B.TF[i]); O, H, L, C, T, atr, lo, hi = bars(B.SYM[i], tfh)
        j = int(np.searchsorted(T, B.T[i]))
        if j >= len(T) - 2 or T[j] != B.T[i] or atr[j] != atr[j]: continue
        hold = 180 if tfh == 24 else 360
        r, k, kd = sim(O, H, L, C, lo, hi, j, int(B.SD[i]), float(atr[j]), soft, hard, hold, tfh, half)
        R[i], H_[i] = r, k
    return R, H_
if __name__ == "__main__":
    which = ARGS[0]
    M = B.BOT if which == "bot" else B.CHECK
    print(f"== {which}")
    R0, H0 = B.lab(1.5, "dc20"); Rs, Hs = outcomes(M)
    ok = ~np.isnan(R0) & ~np.isnan(Rs) & M
    print("проверка: совпадение с меткой исследования", round(float(np.mean(np.abs(R0[ok] - Rs[ok]) < 0.02)), 3), flush=True)
    for nm, kw in (("сейчас: стоп 1.5 касанием", {}), ("стоп 2.0 касанием", {"soft": 2.0}), ("стоп 2.5 касанием", {"soft": 2.5}), ("стоп 3.0 касанием", {"soft": 3.0}),
                   ("стоп 1.5 по закрытию, авар. 3", {"soft": 1.5, "hard": 3.0}), ("стоп 2.0 по закрытию, авар. 3", {"soft": 2.0, "hard": 3.0}),
                   ("стоп 2.0 по закрытию, авар. 4", {"soft": 2.0, "hard": 4.0}), ("стоп 2.0 касанием + половина на +2R", {"soft": 2.0, "half": 2.0}),
                   ("стоп 2.0 касанием + половина на +3R", {"soft": 2.0, "half": 3.0})):
        R, H = outcomes(M, **kw); tr = B.replay(M, R, H); B.line(nm, tr, R, H)
