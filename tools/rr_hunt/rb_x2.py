"""📈 breakout, night round 2: hypotheses on top of the v0.99.663 rule (limit 0.2 ATR / 3 bars, strong breakouts >= 0.6 ATR,
fail exit 2 bars, a quarter at +1R, channel 20 / 15 after +4R, stop 2 ATR, cap 6): the limit depth / wait, the break
strength, the partial share / level, the trailing channel, a time cap, the cap, single-feature entry filters"""
import sys
GRP = sys.argv[1] if len(sys.argv) > 1 else "rule"
import sys, numpy as np
from numba import njit
import rb_h as B
from rb_sim2 import bars, NEX
from wr_eval import stats
F = B.F
@njit(cache=True)
def sim(O, H, L, C, LO, HI, i0, e, s, risk, hold, tfh, ne, ne2, tight_r, part_r, part_f, lvl, fail_k, be_r):
    n = len(C); hs = e - s * risk
    tight = False; best = 0.0; took = False; bed = False
    W = min(hold, n - i0); k = W - 1; ex = C[i0 + k]
    for q in range(W):
        b = i0 + q
        if (s > 0 and L[b] <= hs) or (s < 0 and H[b] >= hs):
            ex = hs if q == 0 or not ((s > 0 and O[b] <= hs) or (s < 0 and O[b] >= hs)) else O[b]; k = q; break
        fav = (H[b] - e) / risk if s > 0 else (e - L[b]) / risk
        if fav > best: best = fav
        if part_r > 0 and not took and best >= part_r:
            took = True; hs = e
        if be_r > 0 and not bed and best >= be_r:
            bed = True; hs = e
        if best >= tight_r: tight = True
        lv = LO[ne2 if tight else ne, b] if s > 0 else HI[ne2 if tight else ne, b]
        if (s > 0 and C[b] < lv) or (s < 0 and C[b] > lv):
            ex = C[b]; k = q; break
        if fail_k > 0 and q < fail_k and not took and ((s > 0 and C[b] < lvl) or (s < 0 and C[b] > lvl)):
            ex = C[b]; k = q; break
    fee = (0.001 * e + 0.0003 * e * (k + 1) * tfh / 24) / risk
    rest = s * (ex - e) / risk
    return ((part_f * part_r + (1 - part_f) * rest) if took else rest) - fee, k + 1
def run(mask, cap=6, lim=0.2, wait=3, min_brk=0.6, part_r=1.0, part_f=0.25, ne=20, ne2=15, tight_r=4.0, stop_k=2.0, fail_k=2,
        hold=None, be_r=0.0, filt=None):
    R = np.full(len(B.T), np.nan); Hh = np.ones(len(B.T), np.int64)
    m = mask & (B.T >= B.START) & (B.BRK >= min_brk)
    if filt is not None: m &= filt
    for i in np.where(m)[0]:
        tfh = int(B.TF[i]); O, H, L, C, T, atr, LO, HI, e200 = bars(B.SYM[i], tfh)
        j = int(np.searchsorted(T, B.T[i]))
        if j >= len(T) - 4 or T[j] != B.T[i] or atr[j] != atr[j]: continue
        s = int(B.SD[i]); N0 = int(B.N[i]); a = float(atr[j])
        lvl = H[j - N0:j].max() if s > 0 else L[j - N0:j].min()
        i0, e = j + 1, O[j + 1]
        if lim > 0:
            lv_ = O[j + 1] - s * lim * a; q0 = -1
            for q in range(1, wait + 1):
                if j + q >= len(C): break
                if (s > 0 and L[j + q] <= lv_) or (s < 0 and H[j + q] >= lv_): q0 = q; break
            if q0 < 0: continue
            i0 = j + q0; e = min(O[i0], lv_) if s > 0 else max(O[i0], lv_)
        hd = hold or (180 if tfh == 24 else 360)
        r, k = sim(O, H, L, C, LO, HI, i0, e, s, stop_k * a, hd, tfh, NEX.index(ne), NEX.index(ne2), tight_r, part_r, part_f, lvl, fail_k, be_r)
        R[i], Hh[i] = r, k + (i0 - j - 1)
    tr = B.replay(m, R, Hh, cap=cap)
    return [(int(B.T[i]), int(B.T[i] + Hh[i] * B.TF[i] * 3600), float(R[i]), int(B.SD[i]), int(i)) for i in tr]
def q(name, side=None):
    return F[name]
if __name__ == "__main__":
    grp = GRP
    SD = B.SD
    if grp == "rule":
        V = [("сейчас (v663)", {}),
             ("лимитка 0.15 ATR", dict(lim=0.15)), ("лимитка 0.25 ATR", dict(lim=0.25)), ("лимитка 0.3 ATR", dict(lim=0.3)),
             ("ждать 2 свечи", dict(wait=2)), ("ждать 5 свечей", dict(wait=5)),
             ("сила ≥ 0.4 ATR", dict(min_brk=0.4)), ("сила ≥ 0.8 ATR", dict(min_brk=0.8)), ("сила ≥ 1.0 ATR", dict(min_brk=1.0)),
             ("частичная 1/3 на +1R", dict(part_f=1/3)), ("частичная 1/4 на +1.5R", dict(part_r=1.5)), ("частичная 1/4 на +0.7R", dict(part_r=0.7)),
             ("без частичной", dict(part_r=0.0)), ("без частичной, б/у на +1R", dict(part_r=0.0, be_r=1.0)),
             ("канал 15 сразу", dict(ne=15)), ("канал 30 / 20 после +4R", dict(ne=30, ne2=20)), ("сужение 20→10 после +4R", dict(ne2=10)),
             ("сужение после +6R", dict(tight_r=6.0)), ("сужение после +3R", dict(tight_r=3.0)),
             ("стоп 1.75 ATR", dict(stop_k=1.75)), ("стоп 2.5 ATR", dict(stop_k=2.5)),
             ("возврат в коридор 1 свеча", dict(fail_k=1)), ("возврат в коридор 3 свечи", dict(fail_k=3)),
             ("лимит 4 на сторону", dict(cap=4)), ("лимит 10 на сторону", dict(cap=10))]
    else:
        def f(nm, op, v): x = F[nm]; return (x > v) if op == ">" else (x < v)
        bl = (F["b_r24"] * SD)          # BTC 24h in the trade's direction
        V = [("сейчас (v663)", {}),
             ("BTC 24ч не против (>-2%)", dict(filt=bl > -2)), ("BTC 24ч по направлению (>0)", dict(filt=bl > 0)),
             ("BTC выше EMA50 для лонгов / ниже для шортов", dict(filt=F["b_e50"] * SD > 0)),
             ("ADX > 20", dict(filt=F["adx"] > 20)), ("ADX < 30", dict(filt=F["adx"] < 30)),
             ("объём z > 1", dict(filt=F["vol_z"] > 1)), ("объём z > 2", dict(filt=F["vol_z"] > 2)),
             ("RSI не перегрет (лонг < 75 / шорт > 25)", dict(filt=np.where(SD > 0, F["rsi14"] < 75, F["rsi14"] > 25))),
             ("фандинг не против (≤0 для лонга / ≥0 шорт)", dict(filt=F["fund"] * SD <= 0)),
             ("день EMA200 по направлению", dict(filt=F["dd_e200"] * SD > 0)),
             ("сила монеты к BTC 24ч по направлению", dict(filt=F["rs24"] * SD > 0)),
             ("сила монеты к BTC 7д по направлению", dict(filt=F["rs168"] * SD > 0)),
             ("не выходные", dict(filt=F["weekend"] < 0.5)),
             ("ATR% < медианы", dict(filt=F["atr_pct"] < np.nanmedian(F["atr_pct"]))),
             ("ATR% > медианы", dict(filt=F["atr_pct"] > np.nanmedian(F["atr_pct"]))),
             ("неделя по направлению (roc168)", dict(filt=F["roc168"] * SD > 0)),
             ("не у годового экстремума (pos365 0.1–0.9)", dict(filt=(F["d_pos365"] > 0.1) & (F["d_pos365"] < 0.9)))]
    for nm_, M, tg in (("бот", B.BOT, 0.45), ("проверка", B.CHECK, 0.50)):
        print(f"\n=== пробой, {nm_}", flush=True)
        for nm, kw in V: stats(nm, run(M, **kw), B.START, tg)
