import numpy as np, warnings; warnings.filterwarnings("ignore")
exec(open("to15k.py").read().split("for fr in (True, False):")[0])
for fr in (True, False):
    r_ = np.where(md != 0, r0 - 0.03, r0) if fr else r0
    f = lambda a, b: simx(t0, t1, r_, st_, sth, buf, md, ci, use, rk, int(np.searchsorted(t0, a)), b, 0.05, wg, 10.0, 20.0, 0.9, 20.0, tbr)
    H = []
    for s in starts:
        hit = None; k = 1
        while s + k * M <= END:
            if f(s, s + k * M)[0] >= 15000: hit = k; break
            k += 1
        H.append(hit)
    avail = (END - starts) / M
    print(f"== {'с трением −0.03R' if fr else 'как в бэктесте'}: стартов {len(starts)} (каждую неделю янв.2023 – сен.2026)")
    for m_ in (3, 6, 9, 12, 18, 24, 30):
        el = avail >= m_
        if el.sum() < 10: continue
        sh = np.mean([h is not None and h <= m_ for h, e in zip(H, el) if e])
        print(f"   за {m_:2d} мес: дошли до $15k {sh*100:3.0f}% стартов (из {int(el.sum())}, где хватало данных)")
    g = np.array([h for h, e in zip(H, avail >= 24) if e and h is not None]); ng = int((avail >= 24).sum())
    print(f"   среди стартов с ≥24 мес данных ({ng}): дошли {len(g)}; месяцев до $15k — 25% {np.percentile(g, 25):.0f}, медиана {np.median(g):.0f}, 75% {np.percentile(g, 75):.0f}, max {g.max()}")
    byy = {}
    for s, h in zip(starts, H):
        y = int(np.datetime64(int(s), 's').astype('datetime64[Y]').astype(int) + 1970); byy.setdefault(y, []).append(h)
    print("   по году старта (медиана месяцев, доля дошедших):", {y: (np.median([x for x in v if x]) if any(v) else None, f"{np.mean([x is not None for x in v])*100:.0f}%") for y, v in byy.items()})
