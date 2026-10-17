import glob, pickle, numpy as np, datetime as dt
from mk import ts
import rb_daily as R
exec(open("rb_cap.py").read().split("CONF = []")[0])
def detail(N, K, g, sk, xn, cap, seeds=20):
    m0 = (NN == N) & (RG < K) & (OWN if g == "own200" else (OWN & WEEK))
    si, xi = R.STOPS.index(sk), R.EXITS.index(xn)
    r = Y[:, si, xi, 0].astype(float); j = Y[:, si, xi, 1]
    print(f"\n== N{N} сжатие<{K} {g} стоп {sk} ATR выход {xn}, лимит {cap} на сторону (медиана по {seeds} перемешиваниям) ==")
    allr = []
    for y in YRS:
        idx = np.where(m0 & YM[y])[0]
        runs = []
        for seed in range(seeds):
            pri = np.random.default_rng(seed).random(len(idx)); o = idx[np.lexsort((pri, T[idx]))]
            busy, act, out = {}, [], []
            for i in o:
                key = (SY[i], SD[i]); t = T[i]
                if busy.get(key, 0) > t or r[i] != r[i]:
                    continue
                act = [a for a in act if a[0] > t]
                if sum(1 for a in act if a[1] == SD[i]) >= cap:
                    continue
                end = t + int(j[i]) * 86400; busy[key] = end; act.append((end, SD[i])); out.append((end, r[i], SD[i], j[i]))
            runs.append(out)
        runs.sort(key=lambda o: np.mean([x[1] for x in o]) if o else 0)
        out = sorted(runs[len(runs) // 2])
        rs = np.array([x[1] for x in out]); c = np.cumsum(rs)
        dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], c])) - np.concatenate([[0], c])))
        lo = np.array([x[1] for x in out if x[2] > 0]); sh = np.array([x[1] for x in out if x[2] < 0])
        mx = 0; ls = 0
        for v in rs:
            ls = ls + 1 if v < 0 else 0; mx = max(mx, ls)
        print(f"{y if y < 2025 else '2025–26'}: {len(rs)} сделок ({len(rs) / WK[y]:.1f}/нед) · {rs.mean():+.2f}R · WR {100 * (rs > 0).mean():.0f}% · итог {rs.sum():+.0f}R · "
              f"просадка {dd:.0f}R · серия стопов {mx} · держится ~{np.mean([x[3] for x in out]):.0f} дн · лонг {lo.mean() if len(lo) else 0:+.2f}R×{len(lo)} шорт {sh.mean() if len(sh) else 0:+.2f}R×{len(sh)} · лучшая {rs.max():+.1f}R")
        allr += list(rs)
    a = np.array(allr)
    print(f"всего: {len(a)} сделок · {a.mean():+.2f}R на сделку · WR {100 * (a > 0).mean():.0f}% · медиана {np.median(a):+.2f}R · сделок ≥5R: {(a >= 5).sum()}")
detail(20, 2.5, "own200", 1.5, "dc20", 6)
detail(20, 2.5, "own200", 1.5, "dc20", 12)
detail(15, 2.5, "own200", 1.5, "dc20", 6)
detail(15, 2.5, "own200", 1.5, "dc20", 12)
