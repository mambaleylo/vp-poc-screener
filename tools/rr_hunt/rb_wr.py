"""📈 breakout: win rate / losing runs — partial takes, break-even, dead-trade exits, caps, a pause after losses.
The current rule: stop 2 ATR, out at the close beyond the 20-bar low/high, 15 after +4R; day + 12h; 6 per side per chart."""
import numpy as np
from numba import njit
import rb_h as B
from rb_sim2 import bars, NEX
from wr_eval import stats, pause
@njit(cache=True)
def sim(O, H, L, C, LO, HI, i0, e, s, a, hold, tfh, ne, tight_r, ne2, part_r, part_f, be_r, dead):
    n = len(C); risk = 2.0 * a; hs = e - s * risk
    tight = False; best = 0.0; took = False
    k = min(hold, n - i0) - 1; ex = C[i0 + k]
    for q in range(min(hold, n - i0)):
        b = i0 + q
        if (s > 0 and L[b] <= hs) or (s < 0 and H[b] >= hs):
            ex = hs if q == 0 or not ((s > 0 and O[b] <= hs) or (s < 0 and O[b] >= hs)) else O[b]; k = q; break
        fav = (H[b] - e) / risk if s > 0 else (e - L[b]) / risk
        if fav > best: best = fav
        if part_r > 0 and not took and best >= part_r:
            took = True; hs = e
        if be_r > 0 and best >= be_r and s * (hs - e) < 0: hs = e
        if best >= tight_r: tight = True
        ch = ne2 if tight else ne
        lv = LO[ch, b] if s > 0 else HI[ch, b]
        if (s > 0 and C[b] < lv) or (s < 0 and C[b] > lv):
            ex = C[b]; k = q; break
        if dead > 0 and q + 1 == dead and best < 1.0:
            ex = C[b]; k = q; break
    rest = (s * (ex - e) - 0.001 * e - 0.0003 * e * (k + 1) * tfh / 24) / risk
    return (part_f * part_r + (1 - part_f) * rest) if took else rest, k + 1
def run(mask, cap=6, part_r=0.0, part_f=0.5, be_r=0.0, dead=0):
    R = np.full(len(B.T), np.nan); Hh = np.ones(len(B.T), np.int64)
    for i in np.where(mask & (B.T >= B.START))[0]:
        tfh = int(B.TF[i]); O, H, L, C, T, atr, LO, HI, e200 = bars(B.SYM[i], tfh)
        j = int(np.searchsorted(T, B.T[i]))
        if j >= len(T) - 2 or T[j] != B.T[i] or atr[j] != atr[j]: continue
        r, k = sim(O, H, L, C, LO, HI, j + 1, O[j + 1], int(B.SD[i]), float(atr[j]), 180 if tfh == 24 else 360, tfh,
                   NEX.index(20), 4.0, NEX.index(15), part_r, part_f, be_r, dead)
        R[i], Hh[i] = r, k
    tr = B.replay(mask, R, Hh, cap=cap)
    return [(int(B.T[i]), int(B.T[i] + Hh[i] * B.TF[i] * 3600), float(R[i]), int(B.SD[i]), int(i)) for i in tr]
if __name__ == "__main__":
    V = [("сейчас (до 6 в сторону на график)", {}),
         ("до 4", dict(cap=4)), ("до 3", dict(cap=3)),
         ("половина на +2R → б/у (режим бота)", dict(part_r=2.0)),
         ("половина на +1R → б/у", dict(part_r=1.0)),
         ("половина на +1.5R → б/у", dict(part_r=1.5)),
         ("треть на +1R → б/у", dict(part_r=1.0, part_f=0.33)),
         ("безубыток после +1R", dict(be_r=1.0)),
         ("безубыток после +1.5R", dict(be_r=1.5)),
         ("закрыть, если за 10 свечей не было +1R", dict(dead=10)),
         ("половина на +1R → б/у, до 4", dict(part_r=1.0, cap=4)),
         ("треть на +1R → б/у, до 4", dict(part_r=1.0, part_f=0.33, cap=4))]
    for nm_, M, tg in (("бот", B.BOT, 0.45), ("проверка (другие длины коридора)", B.CHECK, 0.50)):
        print(f"\n=== {nm_}")
        for nm, kw in V: stats(nm, run(M, **kw), B.START, tg)
        base = run(M)
        for L in (4, 6, 8): stats(f"сейчас + пауза после {L} минусов", pause(base, L), B.START, tg)
        pb = run(M, part_r=1.0, part_f=0.33)
        for L in (4, 6): stats(f"треть на +1R + пауза после {L}", pause(pb, L), B.START, tg)
