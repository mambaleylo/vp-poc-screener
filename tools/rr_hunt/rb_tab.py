import glob, pickle, itertools, numpy as np
from mk import ts
import rb_daily as R
ev = []
for k, fn in enumerate(sorted(glob.glob("rb/*.pkl"))):
    for t, s, f, y in pickle.load(open(fn, "rb")):
        ev.append((t, k, s, f, y))
T = np.array([e[0] for e in ev]); SY = np.array([e[1] for e in ev]); SD = np.array([e[2] for e in ev])
NN = np.array([e[3]["N"] for e in ev]); RG = np.array([e[3]["rg"] for e in ev])
OWN = np.array([bool(e[3]["own200"]) for e in ev]); WEEK = np.array([bool(e[3]["week"]) for e in ev])
Y = np.stack([e[4] for e in ev])
print("events", len(T))
YRS = (2021, 2022, 2023, 2024, 2025)
YM = {y: (T >= ts(y)) & (T < (ts(y + 1) if y < 2025 else ts(2027))) for y in YRS}
WK = {y: ((ts(y + 1) if y < 2025 else ts(2026, 10)) - ts(y)) / (7 * 86400) for y in YRS}
def replay(idx, r, j):
    o = idx[np.argsort(T[idx], kind="stable")]
    busy, out = {}, []
    for i in o:
        key = (SY[i], SD[i])
        if busy.get(key, 0) > T[i] or r[i] != r[i]:
            continue
        busy[key] = T[i] + int(j[i]) * 86400
        out.append((busy[key], float(r[i])))
    return out
GATES = {"—": np.ones(len(T), bool), "own200": OWN, "week": WEEK, "own200+week": OWN & WEEK, "own200 лонг": OWN & (SD > 0)}
res = []
for N in R.NS:
    for K in R.KS:
        base = (NN == N) & (RG < K)
        for gn, g in GATES.items():
            m0 = base & g
            for si, sk in enumerate(R.STOPS):
                for xi, xn in enumerate(R.EXITS):
                    r = Y[:, si, xi, 0].astype(float); j = Y[:, si, xi, 1]
                    per = []
                    for y in YRS:
                        out = sorted(replay(np.where(m0 & YM[y])[0], r, j))
                        rs = np.array([o[1] for o in out])
                        if len(rs) >= 8:
                            c = np.cumsum(rs); dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], c])) - np.concatenate([[0], c])))
                            per.append((rs.mean(), len(rs) / WK[y], dd, (rs > 0).mean() * 100))
                        else:
                            per.append((np.nan, len(rs) / WK[y], 0, 0))
                    tr = [p[0] for p in per[:3]]
                    res.append((np.nanmin(tr) if not np.isnan(tr).any() else -9, N, K, gn, sk, xn, per))
pickle.dump(res, open("rb_res.pkl", "wb"))
res.sort(key=lambda r: -r[0])
def line(r):
    sc, N, K, gn, sk, xn, per = r
    return f"N{N:2d} сжатие<{K} {gn:11s} стоп {sk} {xn:4s} || " + " | ".join(f"{y}: {p[0]:+.2f}R×{p[1]:.1f}/нед WR{p[3]:.0f} dd{p[2]:.0f}" for y, p in zip(YRS, per))
print("== выбор по худшему году 2021–23; 2024 и 2025–26 — проверка ==")
for r in res[:40]:
    print(line(r))
good = [r for r in res if all(p[0] == p[0] and p[0] >= 0.5 for p in r[6]) and all(p[1] >= 0.7 for p in r[6])]
good.sort(key=lambda r: -np.mean([p[0] for p in r[6]]))
print(f"\n== в плюсе ≥+0.5R каждый год и ≥0.7 сделки/нед: {len(good)} вариантов; лучшие по среднему ==")
for r in good[:25]:
    print(line(r))
