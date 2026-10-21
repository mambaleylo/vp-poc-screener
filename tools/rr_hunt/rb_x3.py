"""📈 breakout, night round 3: pyramiding on the v0.99.663 rule — one more unit of the same size when the price reached
+add_r R (intrabar), its stop add_stop R below the add (or at the first entry), the same trend exit (channel 20 / 15
after +4R, the time cap); R in units of the first risk"""
import numpy as np
from numba import njit
import rb_h as B
from rb_sim2 import bars, NEX
from wr_eval import stats
@njit(cache=True)
def sim(O, H, L, C, LO, HI, i0, e, s, risk, hold, tfh, ne, ne2, part_r, part_f, lvl, fail_k, add_r, add_stop):
    n = len(C); hs = e - s * risk
    tight = False; best = 0.0; took = False
    added = False; ap = 0.0; ast = 0.0; aout = False; ar = 0.0; ak = 0
    W = min(hold, n - i0); k = W - 1; ex = C[i0 + k]
    for q in range(W):
        b = i0 + q
        if added and not aout and ((s > 0 and L[b] <= ast) or (s < 0 and H[b] >= ast)):
            g = (s > 0 and O[b] <= ast) or (s < 0 and O[b] >= ast)
            aout = True; ar = s * ((O[b] if g else ast) - ap) / risk; ak = q
        if (s > 0 and L[b] <= hs) or (s < 0 and H[b] >= hs):
            ex = hs if q == 0 or not ((s > 0 and O[b] <= hs) or (s < 0 and O[b] >= hs)) else O[b]; k = q; break
        fav = (H[b] - e) / risk if s > 0 else (e - L[b]) / risk
        if fav > best: best = fav
        if part_r > 0 and not took and best >= part_r:
            took = True; hs = e
        if add_r > 0 and not added and best >= add_r:
            added = True; ap = e + s * add_r * risk; ast = (ap - s * add_stop * risk) if add_stop > 0 else e
        if best >= 4.0: tight = True
        lv = LO[ne2 if tight else ne, b] if s > 0 else HI[ne2 if tight else ne, b]
        if (s > 0 and C[b] < lv) or (s < 0 and C[b] > lv):
            ex = C[b]; k = q; break
        if fail_k > 0 and q < fail_k and not took and ((s > 0 and C[b] < lvl) or (s < 0 and C[b] > lvl)):
            ex = C[b]; k = q; break
    fee = (0.001 * e + 0.0003 * e * (k + 1) * tfh / 24) / risk
    rest = s * (ex - e) / risk
    r = ((part_f * part_r + (1 - part_f) * rest) if took else rest) - fee
    if added:
        if not aout: ar = s * (ex - ap) / risk; ak = k
        r += ar - (0.001 * ap + 0.0003 * ap * (ak + 1) * tfh / 24) / risk
    return r, k + 1
def run(mask, add_r=0.0, add_stop=1.0, cap=6, lim=0.2, wait=3, min_brk=0.6):
    R = np.full(len(B.T), np.nan); Hh = np.ones(len(B.T), np.int64)
    m = mask & (B.T >= B.START) & (B.BRK >= min_brk)
    for i in np.where(m)[0]:
        tfh = int(B.TF[i]); O, H, L, C, T, atr, LO, HI, e200 = bars(B.SYM[i], tfh)
        j = int(np.searchsorted(T, B.T[i]))
        if j >= len(T) - 4 or T[j] != B.T[i] or atr[j] != atr[j]: continue
        s = int(B.SD[i]); N0 = int(B.N[i]); a = float(atr[j])
        lvl = H[j - N0:j].max() if s > 0 else L[j - N0:j].min()
        lv_ = O[j + 1] - s * lim * a; q0 = -1
        for q in range(1, wait + 1):
            if j + q >= len(C): break
            if (s > 0 and L[j + q] <= lv_) or (s < 0 and H[j + q] >= lv_): q0 = q; break
        if q0 < 0: continue
        i0 = j + q0; e = min(O[i0], lv_) if s > 0 else max(O[i0], lv_)
        r, k = sim(O, H, L, C, LO, HI, i0, e, s, 2.0 * a, 180 if tfh == 24 else 360, tfh, NEX.index(20), NEX.index(15), 1.0, 0.25, lvl, 2, add_r, add_stop)
        R[i], Hh[i] = r, k + (i0 - j - 1)
    tr = B.replay(m, R, Hh, cap=cap)
    return [(int(B.T[i]), int(B.T[i] + Hh[i] * B.TF[i] * 3600), float(R[i]), int(B.SD[i]), int(i)) for i in tr]
if __name__ == "__main__":
    V = [("сейчас (v663)", {}), ("добор на +2R, стоп добора 1R", dict(add_r=2.0)), ("добор на +2R, стоп добора на входе", dict(add_r=2.0, add_stop=0.0)),
         ("добор на +3R, стоп добора 1R", dict(add_r=3.0)), ("добор на +3R, стоп 1.5R", dict(add_r=3.0, add_stop=1.5)),
         ("добор на +4R, стоп добора 2R", dict(add_r=4.0, add_stop=2.0)), ("добор на +1.5R, стоп 1R", dict(add_r=1.5))]
    for nm_, M, tg in (("бот", B.BOT, 0.45), ("проверка", B.CHECK, 0.50)):
        print(f"\n=== пробой, {nm_}", flush=True)
        for nm, kw in V: stats(nm, run(M, **kw), B.START, tg)
