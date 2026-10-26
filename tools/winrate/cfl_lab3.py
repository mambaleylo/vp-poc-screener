"""🔄 Классика наоборот lab, round 3 — on the deployed rule (longs only, 96 h, take 4R, cap 20): the stop's length, the
close stop (4h / 1d close beyond the soft stop, an emergency stop by a touch), break-even, a trailing stop, a partial
take, the take / hold, a limit entry below the hour's open. R in units of the soft stop (the bot sizes on it); bot coins
and check coins; per year; worst trade and R / std."""
import numpy as np
exec(open("cfl_lab.py").read().split('if __name__ == "__main__":')[0].replace("@njit(cache=True)", "@njit"))
from numba import njit
@njit
def walk2(Tb, O, H, L, C, jE, s, datr, sk, hard, ctf, take, hold, be_at, be_to, tr_at, tr_d, p_at, p_fr, p_be, lim, wait):
    d = datr / 100; j0 = jE
    if lim > 0:
        px = O[jE] * (1 - s * lim * d); f = -1
        for q in range(wait):
            b = jE + q
            if b >= len(C): break
            if (s > 0 and L[b] <= px) or (s < 0 and H[b] >= px):
                f = b; break
        if f < 0: return np.nan, wait
        fill = min(px, O[f]) if s > 0 else max(px, O[f]); j0 = f
    else:
        fill = O[jE]
    risk = fill * sk * d; stop = fill - s * risk
    hs = fill - s * hard * fill * d if hard > 0 else stop
    tp = fill + s * take * risk if take > 0 else (np.inf if s > 0 else -np.inf)
    e = min(len(C), j0 + hold); rem = 1.0; real = 0.0; moved = False; cur = stop; best = fill; parted = False
    k = e - 1 - j0; done = False
    for q in range(e - j0):
        b = j0 + q
        lvl = cur if (moved or ctf == 0) else hs
        if (s > 0 and L[b] <= lvl) or (s < 0 and H[b] >= lvl):
            gap = (s > 0 and O[b] <= lvl) or (s < 0 and O[b] >= lvl)
            ex = O[b] if (gap and q > 0) else lvl
            real += rem * s * (ex - fill) / risk; k = q; done = True; break
        if q > 0 and ((s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp)):
            real += rem * take; k = q; done = True; break
        if p_at > 0 and not parted and q > 0 and ((s > 0 and H[b] >= fill + s * p_at * risk) or (s < 0 and L[b] <= fill + s * p_at * risk)):
            real += p_fr * p_at; rem -= p_fr; parted = True
            if p_be and (not moved or s * (fill - cur) > 0):
                cur = fill; moved = True
        if ctf > 0 and not moved and (Tb[b] + 3600) % (ctf * 3600) == 0 and s * (C[b] - stop) < 0:
            real += rem * s * (C[b] - fill) / risk; k = q; done = True; break
        if be_at > 0 and s * (C[b] - fill) >= be_at * risk:
            ns = fill + s * be_to * risk
            if not moved or s * (ns - cur) > 0:
                cur = ns; moved = True
        if tr_at > 0:
            best = max(best, H[b]) if s > 0 else min(best, L[b])
            if s * (best - fill) >= tr_at * risk:
                ns = best - s * tr_d * fill * d
                if not moved or s * (ns - cur) > 0:
                    cur = ns; moved = True
    if not done:
        real += rem * s * (C[e - 1] - fill) / risk
    return real - (0.001 + 0.0003 * (k + 1) / 24) * fill / risk, k + 1 + (j0 - jE)
DEF = dict(sk=1.0, hard=0.0, ctf=0, take=4.0, hold=96, be_at=0.0, be_to=0.0, tr_at=0.0, tr_d=0.0, p_at=0.0, p_fr=0.0, p_be=False, lim=0.0, wait=0)
OUT = {}
def run3(nm, q=0.997, side=1, cap=20, quiet=False, **kw):
    if q not in TH: TH[q] = thr_days(q)
    th = TH[q]; p = dict(DEF); p.update(kw); res = []
    for grp in (True, False):
        c = np.where((BOT == grp) & np.isfinite(SC) & (T >= ts(2023)) & (T < ts(2026, 10)))[0]
        c = c[SC[c] >= np.array([th.get(int(t // 86400), np.inf) for t in T[c]])]
        c = c[np.array([T[i] - FIRST[SYM[i]] >= 90 * 86400 for i in c], bool)]
        if side: c = c[-SIDE[c] == side]
        R, K = {}, {}
        for k in sorted(set(SYM[c])):
            Tb, O, H, L, C_, V = bars(k)
            for i in c[SYM[c] == k]:
                jE = int(J[i]) + 1
                if jE + 1 < len(C_):
                    r, kk = walk2(Tb, O, H, L, C_, jE, -int(SIDE[i]), float(DA[i]), p["sk"], p["hard"], p["ctf"], p["take"], p["hold"], p["be_at"], p["be_to"],
                                  p["tr_at"], p["tr_d"], p["p_at"], p["p_fr"], p["p_be"], p["lim"], p["wait"])
                    R[i], K[i] = r, kk
        cc = np.array([i for i in c if i in R], np.int64); oo = cc[np.lexsort((-SC[cc], T[cc]))]
        busy, act, sel = {}, [], []
        for i in oo:
            t = T[i]; key = (SYM[i], SIDE[i])
            if busy.get(key, 0) > t: continue
            act = [a for a in act if a[0] > t]
            if sum(1 for a in act if a[1] == SIDE[i]) >= cap: continue
            end = t + int(K[i]) * 3600; busy[key] = end
            if not np.isfinite(R[i]): continue   # a limit not filled: the slot was held while it waited
            act.append((end, SIDE[i])); sel.append(i)
        sel = np.array(sel, np.int64); r = np.array([R[i] for i in sel]); y = (T[sel].astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970)
        res.append((sel, r, y, np.array([K[i] for i in sel])))
    (sb, rb, yb, kb), (sc_, rc, yc, kc) = res
    OUT[nm] = (sb, rb, kb, sc_, rc, kc)
    if not quiet:
        print(f"  {nm:36s} бот n {len(rb):3d} {rb.mean():+.3f}R WR {np.mean(rb > 0)*100:3.0f}% ΣR/год {rb.sum() / 3.75:+5.1f} R/σ {rb.mean() / rb.std():.2f} худш {rb.min():+.1f} | контр. n {len(rc):3d} {rc.mean():+.3f}R ΣR/год {rc.sum() / 3.75:+5.1f} | "
              + " ".join(f"{Y % 100}:{rb[yb == Y].mean():+.2f}" for Y in range(2023, 2027) if (yb == Y).any()), flush=True)
if __name__ == "__main__":
    print("== база (как в боте v0.99.740)"); run3("B: 1 dATR, 4R, 96ч")
    print("== длина стопа (тейк 4R от стопа)")
    for sk in (0.5, 0.75, 1.25, 1.5, 2.0, 2.5): run3(f"стоп {sk} dATR", sk=sk)
    print("== длина стопа (тейк на том же месте: 4 dATR)")
    for sk in (0.75, 1.5, 2.0): run3(f"стоп {sk}, тейк 4 dATR", sk=sk, take=4.0 / sk)
    print("== стоп по закрытию свечи + аварийный по касанию")
    for ctf in (4, 24):
        for sk, hd in ((1.0, 2.0), (1.0, 3.0), (0.75, 2.0), (1.5, 3.0)): run3(f"закр. {ctf}ч за {sk}, авар. {hd} dATR", sk=sk, hard=hd, ctf=ctf)
    print("== безубыток")
    for a, t in ((1.0, 0.0), (2.0, 0.0), (3.0, 0.0), (2.0, 1.0), (3.0, 1.0)): run3(f"после +{a}R стоп в {'+' + str(t) + 'R' if t else 'безубыток'}", be_at=a, be_to=t)
    print("== трейлинг (от максимума, dATR)")
    for a, dd in ((1.0, 1.5), (2.0, 1.0), (2.0, 2.0), (3.0, 1.0)): run3(f"после +{a}R трейл {dd} dATR", tr_at=a, tr_d=dd)
    run3("трейл 2 dATR сразу, без тейка", tr_at=0.001, tr_d=2.0, take=0.0)
    print("== частичный тейк")
    run3("половина на 2R", p_at=2.0, p_fr=0.5); run3("половина на 2R + безубыток", p_at=2.0, p_fr=0.5, p_be=True)
    run3("треть на 1R", p_at=1.0, p_fr=1 / 3); run3("треть на 1R + безубыток", p_at=1.0, p_fr=1 / 3, p_be=True)
    print("== тейк / держим")
    for tk in (3.0, 5.0, 6.0, 8.0): run3(f"тейк {tk}R", take=tk)
    run3("без тейка (выход по времени)", take=0.0)
    for hd in (72, 120, 144, 168): run3(f"держим {hd}ч", hold=hd)
    run3("тейк 6R, 144ч", take=6.0, hold=144)
    print("== вход лимиткой ниже открытия часа")
    for lm, w in ((0.1, 4), (0.25, 4), (0.25, 12), (0.5, 12)): run3(f"лимитка −{lm} dATR, ждём {w}ч", lim=lm, wait=w)
    print("== обратная сторона с новыми выходами")
    run3("шорты (против покупок), 96ч, 4R", side=-1)
