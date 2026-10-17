import glob, pickle, json, numpy as np, datetime as dt
from collections import defaultdict
from mk import ts
import importlib, os
YRS = (2021, 2022, 2023, 2024, 2025)
WK = {y: ((ts(y + 1) if y < 2025 else ts(2026, 10)) - ts(y)) / (7 * 86400) for y in YRS}
OUT = {}
for TFH, N0, K0 in ((24, 20, 2.5), (12, 30, 4.0)):
    os.environ["TFH"] = str(TFH)
    import rb_tf; importlib.reload(rb_tf)
    ev = []
    for k, fn in enumerate(sorted(glob.glob(f"rbtf{TFH}/*.pkl"))):
        for t, s, f, x, y in pickle.load(open(fn, "rb")):
            if f["N"] == N0 and f["rg"] < K0 and f["own200"]:
                ev.append((t, k, s, f["brk"], y))
    T = np.array([e[0] for e in ev]); SY = np.array([e[1] for e in ev]); SD = np.array([e[2] for e in ev]); BRK = np.array([e[3] for e in ev])
    Y = np.stack([e[4] for e in ev])
    for xn in ("dc20", "half2dc20"):
        si, xi = rb_tf.STOPS.index(1.5), rb_tf.EXITS.index(xn)
        r = Y[:, si, xi, 0].astype(float); j = Y[:, si, xi, 1]
        years, allt = {}, []
        for yy in YRS:
            idx = np.where((T >= ts(yy)) & (T < (ts(yy + 1) if yy < 2025 else ts(2027))))[0]
            o = idx[np.lexsort((-BRK[idx], T[idx]))]
            busy, act, out = {}, [], []
            for i in o:
                kk = (SY[i], SD[i]); t = T[i]
                if busy.get(kk, 0) > t or r[i] != r[i]:
                    continue
                act = [a for a in act if a[0] > t]
                if sum(1 for a in act if a[1] == SD[i]) >= 6:
                    continue
                end = t + int(j[i]) * TFH * 3600; busy[kk] = end; act.append((end, SD[i])); out.append((end, r[i], j[i]))
            out.sort(); rs = np.array([x[1] for x in out]); c = np.cumsum(rs)
            dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], c])) - np.concatenate([[0], c])))
            years[str(yy)] = {"n": len(rs), "avg": round(float(rs.mean()), 2), "wk": round(len(rs) / WK[yy], 1), "sum": round(float(rs.sum()), 1),
                              "dd": round(dd, 1), "wr": round(float((rs > 0).mean() * 100), 1), "days": round(float(np.mean([x[2] for x in out]) * TFH / 24), 0),
                              "best": round(float(rs.max()), 1)}
            allt += out
        mx = ls = 0
        for e, rr, jj in sorted(allt):
            ls = ls + 1 if rr < 0 else 0; mx = max(mx, ls)
        OUT[f"{TFH}_{xn}"] = {"years": years, "max_losing_streak": mx}
        a = np.array([x[1] for x in allt])
        print(TFH, xn, f"{a.mean():+.2f}R WR{(a > 0).mean() * 100:.0f} n{len(a)} серия{mx}", " | ".join(f"{y}: {v['avg']:+.2f}×{v['wk']} WR{v['wr']:.0f} dd{v['dd']:.0f}" for y, v in years.items()))
json.dump(OUT, open("rbx2_research.json", "w"), separators=(",", ":"))
