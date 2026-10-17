import json, numpy as np, datetime as dt
from collections import defaultdict
exec(open("rb_cap.py").read().split("CONF = []")[0])
m0 = (NN == 20) & (RG < 2.5) & OWN
si, xi = R.STOPS.index(1.5), R.EXITS.index("dc20")
r = Y[:, si, xi, 0].astype(float); j = Y[:, si, xi, 1]
years, allt = {}, []
for y in YRS:
    idx = np.where(m0 & YM[y])[0]
    o = idx[np.lexsort((-BRK[idx], T[idx]))]
    busy, act, out = {}, [], []
    for i in o:
        kk = (SY[i], SD[i]); t = T[i]
        if busy.get(kk, 0) > t or r[i] != r[i]:
            continue
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == SD[i]) >= 6:
            continue
        end = t + int(j[i]) * 86400; busy[kk] = end; act.append((end, SD[i])); out.append((end, r[i], SD[i], j[i]))
    out.sort(); rs = np.array([x[1] for x in out]); c = np.cumsum(rs)
    dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], c])) - np.concatenate([[0], c])))
    years[str(y)] = {"n": len(rs), "avg": round(float(rs.mean()), 2), "wk": round(len(rs) / WK[y], 1), "sum": round(float(rs.sum()), 1), "dd": round(dd, 1),
                     "wr": round(float((rs > 0).mean() * 100), 1), "days": round(float(np.mean([x[3] for x in out])), 0), "best": round(float(rs.max()), 1)}
    allt += out
M = defaultdict(float); MN = defaultdict(int)
for e, rr, s, jj in allt:
    k = dt.datetime.utcfromtimestamp(e).strftime("%Y-%m"); M[k] += rr; MN[k] += 1
ms = sorted(M); sums = [M[k] for k in ms]
mx = ls = 0
for e, rr, s, jj in sorted(allt):
    ls = ls + 1 if rr < 0 else 0; mx = max(mx, ls)
res = {"years": years, "pos_months": sum(1 for s in sums if s > 0), "all_months": len(ms), "max_losing_streak": mx,
       "months": [[k, MN[k], round(M[k], 1)] for k in ms if k >= "2025-01"]}
print(json.dumps(res, ensure_ascii=False))
json.dump(res, open("rbx_research.json", "w"), ensure_ascii=False, separators=(",", ":"))
