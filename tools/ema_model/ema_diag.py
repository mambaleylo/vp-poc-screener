import numpy as np
import ema_h as E
d = E.d
def diag(q):
    idx = E.cand(q); R, K, KD = E.outcomes(idx); tr = E.replay(idx, R, K)
    r = R[tr]
    print(f"\n== q {q}: {len(tr)} сделок, ср.R {r.mean():+.3f}, WR {np.mean(r>0)*100:.0f}%")
    def grp(name, key):
        v = key[tr]
        for u in sorted(set(v.tolist())):
            m = v == u
            print(f"   {name} {u!s:>8}: {m.sum():5d} сд. ср.R {r[m].mean():+.3f} WR {np.mean(r[m]>0)*100:3.0f}% стопов {np.mean(np.isin(KD[tr][m], (0,1)))*100:3.0f}% | " +
                  " ".join(f"{r[m & (E.YR[tr]==y)].mean():+.2f}" if (m & (E.YR[tr]==y)).any() else "  —  " for y in (2022, 2023, 2024, 2025)))
    grp("график", d.tf_s.values); grp("EMA", d.n_i.values); grp("сторона", d.side.values)
    def qgrp(name, v, edges):
        v = v[tr]
        for a, b in zip(edges[:-1], edges[1:]):
            m = (v >= a) & (v < b)
            if m.sum(): print(f"   {name} {a:+7.1f}..{b:+7.1f}: {m.sum():5d} сд. ср.R {r[m].mean():+.3f} WR {np.mean(r[m]>0)*100:3.0f}%")
    qgrp("BTC 24ч по стороне", d.s_b24.values, [-99, -4, -2, -1, 0, 1, 2, 4, 99])
    qgrp("цена vs EMA200 дня (по стороне)", d.s_d_ema200.values, [-99, -20, -10, -5, 0, 5, 10, 20, 99])
    qgrp("монета за 24ч (по стороне)", d.s_r24.values, [-99, -10, -5, -2, 0, 2, 5, 10, 99])
    # stops: wick vs close (1h close back inside the stop)
    st = tr[KD[tr] == 0]
    w = 0
    for i in st:
        O, H, L, C = E.bars(d.sym.values[i]); b = int(d.j.values[i]) + int(K[i]) - 1
        stop = d.lv.values[i] - d.side.values[i] * d.lv.values[i] * 0.75 * d.datr.values[i] / 100
        w += (C[b] > stop) if d.side.values[i] > 0 else (C[b] < stop)
    print(f"   стопов {len(st)}: часовая свеча закрылась обратно за стопом (фитиль) {w}")
for q in (0.97, 0.90):
    diag(q)
