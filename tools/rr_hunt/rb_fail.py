"""📈 breakout: the trades that go straight to the stop (the user: "часто в стопах, когда идёт сразу после входа только в
сторону стопа"). How many stops never saw +x R, and the fixes: an exit at the close back inside the range, a confirmation
bar, a retest entry, a stop beyond the range, a strong-breakout filter. On top of the current rule (stop 2 ATR, channel
20 / 15 after +4R, a quarter at +1R)."""
import sys, numpy as np
from numba import njit
import rb_h as B
from rb_sim2 import bars, NEX
from wr_eval import stats
@njit(cache=True)
def sim(O, H, L, C, LO, HI, i0, e, s, risk, hold, tfh, ne, ne2, part_r, part_f, lvl, fail_k, fail_buf):
    """-> R, bars, kind (0 stop, 1 be, 2 trend, 3 time, 4 failed breakout), best R seen, bars to the end"""
    n = len(C); hs = e - s * risk
    tight = False; best = 0.0; took = False
    W = min(hold, n - i0); k = W - 1; ex = C[i0 + k]; kind = 3
    for q in range(W):
        b = i0 + q
        if (s > 0 and L[b] <= hs) or (s < 0 and H[b] >= hs):
            ex = hs if q == 0 or not ((s > 0 and O[b] <= hs) or (s < 0 and O[b] >= hs)) else O[b]; k = q; kind = 1 if took else 0; break
        fav = (H[b] - e) / risk if s > 0 else (e - L[b]) / risk
        if fav > best: best = fav
        if part_r > 0 and not took and best >= part_r:
            took = True; hs = e
        if best >= 4.0: tight = True
        lv = LO[ne2 if tight else ne, b] if s > 0 else HI[ne2 if tight else ne, b]
        if (s > 0 and C[b] < lv) or (s < 0 and C[b] > lv):
            ex = C[b]; k = q; kind = 2; break
        if fail_k > 0 and q < fail_k and not took and ((s > 0 and C[b] < lvl - fail_buf) or (s < 0 and C[b] > lvl + fail_buf)):
            ex = C[b]; k = q; kind = 4; break
    fee = (0.001 * e + 0.0003 * e * (k + 1) * tfh / 24) / risk
    rest = s * (ex - e) / risk
    return ((part_f * part_r + (1 - part_f) * rest) if took else rest) - fee, k + 1, kind, best
def run(mask, cap=6, part=True, fail_k=0, fail_buf=0.0, entry="next", retest=0, stop="atr", stop_k=2.0, min_brk=None, out=None):
    R = np.full(len(B.T), np.nan); Hh = np.ones(len(B.T), np.int64)
    for i in np.where(mask & (B.T >= B.START))[0]:
        if min_brk is not None and B.BRK[i] < min_brk: continue
        tfh = int(B.TF[i]); O, H, L, C, T, atr, LO, HI, e200 = bars(B.SYM[i], tfh)
        j = int(np.searchsorted(T, B.T[i]))
        if j >= len(T) - 4 or T[j] != B.T[i] or atr[j] != atr[j]: continue
        s = int(B.SD[i]); N0 = int(B.N[i]); a = float(atr[j])
        lvl = H[j - N0:j].max() if s > 0 else L[j - N0:j].min()
        opp = L[j - N0:j].min() if s > 0 else H[j - N0:j].max()
        i0, e = j + 1, O[j + 1]
        if entry == "confirm":       # the next bar must close beyond the level too; in at the open after it
            if (s > 0 and C[j + 1] <= lvl) or (s < 0 and C[j + 1] >= lvl): continue
            i0, e = j + 2, O[j + 2]
        elif entry == "lim":         # v0.99.662 night: a limit `retest` ATR x 0.1 better than the next open, 3 bars
            lv_ = O[j + 1] - s * (retest / 10.0) * a; q0 = -1
            for q in range(1, 4):
                if j + q >= len(C): break
                if (s > 0 and L[j + q] <= lv_) or (s < 0 and H[j + q] >= lv_): q0 = q; break
            if q0 < 0: continue
            i0 = j + q0; e = min(O[i0], lv_) if s > 0 else max(O[i0], lv_)
        elif entry == "retest":      # a limit at the level, waiting `retest` bars
            q0 = -1
            for q in range(1, retest + 1):
                if j + q >= len(C): break
                if (s > 0 and L[j + q] <= lvl) or (s < 0 and H[j + q] >= lvl): q0 = q; break
            if q0 < 0: continue
            i0 = j + q0; e = min(O[i0], lvl) if s > 0 else max(O[i0], lvl)
        if stop == "atr": risk = stop_k * a
        elif stop == "range_mid": risk = max(s * (e - (lvl + opp) / 2), 0.5 * a)
        elif stop == "range_edge": risk = max(s * (e - lvl) + 0.5 * a, 0.5 * a)      # 0.5 ATR back inside the range
        r, k, kind, best = sim(O, H, L, C, LO, HI, i0, e, s, risk, 180 if tfh == 24 else 360, tfh, NEX.index(20), NEX.index(15),
                               1.0 if part else 0.0, 0.25, lvl, fail_k, fail_buf * a)
        R[i], Hh[i] = r, k + (i0 - j - 1)
        if out is not None: out[i] = (kind, best, k)
    tr = B.replay(mask, R, Hh, cap=cap)
    return [(int(B.T[i]), int(B.T[i] + Hh[i] * B.TF[i] * 3600), float(R[i]), int(B.SD[i]), int(i)) for i in tr]
if __name__ == "__main__":
    # 1. the diagnosis: how the stops looked
    info = {}; tr = run(B.BOT, out=info)
    st = [x for x in tr if info[x[4]][0] == 0]
    bests = np.array([info[x[4]][1] for x in st]); ks = np.array([info[x[4]][2] for x in st])
    print(f"сделок {len(tr)}, стопов {len(st)} ({len(st)/len(tr)*100:.0f}%)")
    for th in (0.25, 0.5, 1.0): print(f"  стопы, где цена не прошла и +{th}R в плюс: {np.mean(bests < th)*100:.0f}%")
    for kk in (1, 2, 3, 5): print(f"  стоп за первые {kk} свечи: {np.mean(ks <= kk)*100:.0f}%")
    for nm_, M, tg in (("бот", B.BOT, 0.45), ("проверка (другие длины коридора)", B.CHECK, 0.50)):
        print(f"\n=== {nm_}")
        V = [("сейчас (¼ на +1R)", {}),
             ("выход: закрытие обратно в коридоре, первые 2 свечи", dict(fail_k=2)),
             ("выход: закрытие обратно в коридоре, первые 3 свечи", dict(fail_k=3)),
             ("выход: закрытие обратно в коридоре, первые 5 свечей", dict(fail_k=5)),
             ("выход: закрытие в коридоре глубже 0.5 ATR, 3 свечи", dict(fail_k=3, fail_buf=0.5)),
             ("вход после подтверждения следующей свечой", dict(entry="confirm")),
             ("вход лимиткой на ретесте границы (ждать 3)", dict(entry="retest", retest=3)),
             ("вход на ретесте (ждать 6)", dict(entry="retest", retest=6)),
             ("стоп 1.5 ATR", dict(stop_k=1.5)), ("стоп 2.5 ATR", dict(stop_k=2.5)),
             ("стоп за серединой коридора", dict(stop="range_mid")),
             ("стоп 0.5 ATR внутрь коридора", dict(stop="range_edge")),
             ("сильный пробой (закрытие за границей ≥ 0.3 ATR)", dict(min_brk=0.3)),
             ("сильный пробой ≥ 0.6 ATR", dict(min_brk=0.6)),
             ("подтверждение + выход по возврату в коридор 3", dict(entry="confirm", fail_k=3))]
        for nm, kw in V: stats(nm, run(M, **kw), B.START, tg)
