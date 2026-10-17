"""range breakout per chart: the rule grid with a cap (strongest breakout first); picked on 2021–23"""
import os, sys, glob, pickle, numpy as np
from mk import ts
TFH = int(os.environ.get("TFH", 4))
import rb_tf as R
ev = []
for k, fn in enumerate(sorted(glob.glob(f"rbtf{TFH}/*.pkl"))):
    for t, s, f, x, y in pickle.load(open(fn, "rb")):
        ev.append((t, k, s, f, y))
T = np.array([e[0] for e in ev]); SY = np.array([e[1] for e in ev]); SD = np.array([e[2] for e in ev])
NN = np.array([e[3]["N"] for e in ev]); RG = np.array([e[3]["rg"] for e in ev]); BRK = np.array([e[3]["brk"] for e in ev])
OWN = np.array([bool(e[3]["own200"]) for e in ev]); D2 = np.array([bool(e[3]["d200"]) for e in ev])
Y = np.stack([e[4] for e in ev])
YRS = (2021, 2022, 2023, 2024, 2025)
YM = {y: (T >= ts(y)) & (T < (ts(y + 1) if y < 2025 else ts(2027))) for y in YRS}
WK = {y: ((ts(y + 1) if y < 2025 else ts(2026, 10)) - ts(y)) / (7 * 86400) for y in YRS}
def replay(idx, r, j, cap):
    o = idx[np.lexsort((-BRK[idx], T[idx]))]
    busy, act, out = {}, [], []
    for i in o:
        kk = (SY[i], SD[i]); t = T[i]
        if busy.get(kk, 0) > t or r[i] != r[i]:
            continue
        act = [a for a in act if a[0] > t]
        if cap and sum(1 for a in act if a[1] == SD[i]) >= cap:
            continue
        end = t + int(j[i]) * TFH * 3600; busy[kk] = end; act.append((end, SD[i])); out.append((end, float(r[i])))
    return out
GATES = {"own200": OWN, "d200": D2, "own+d200": OWN & D2}
res = []
for N in R.NS:
    for K in (2.0, 2.5, 3.0, 4.0):
        for gn, g in GATES.items():
            m0 = (NN == N) & (RG < K) & g
            for si, sk in enumerate(R.STOPS):
                for xi, xn in enumerate(R.EXITS):
                    r = Y[:, si, xi, 0].astype(float); j = Y[:, si, xi, 1]
                    for cap in (6, 12):
                        per = []
                        for y in YRS:
                            out = sorted(replay(np.where(m0 & YM[y])[0], r, j, cap))
                            rs = np.array([o[1] for o in out])
                            if len(rs) >= 8:
                                c = np.cumsum(rs); dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], c])) - np.concatenate([[0], c])))
                                per.append((rs.mean(), len(rs) / WK[y], dd, (rs > 0).mean() * 100))
                            else:
                                per.append((np.nan, len(rs) / WK[y], 0, 0))
                        tr = [p[0] for p in per[:3]]
                        res.append((np.nanmin(tr) if not np.isnan(tr).any() else -9, N, K, gn, sk, xn, cap, per))
pickle.dump(res, open(f"rbtf{TFH}_res.pkl", "wb"))
res.sort(key=lambda r: -r[0])
def line(r):
    sc, N, K, gn, sk, xn, cap, per = r
    return f"[{TFH}ч] N{N} <{K} {gn:8s} стоп {sk} {xn:9s} лимит {cap:2d} || " + " | ".join(f"{p[0]:+.2f}R×{p[1]:.1f} WR{p[3]:.0f} dd{p[2]:.0f}" for p in per)
print(f"== {TFH}ч: выбор по худшему году 2021–23; 2024 и 2025–26 — проверка ==")
for r in res[:25]:
    print(line(r))
good = [r for r in res if all(p[0] == p[0] and p[0] >= 0.3 for p in r[7]) and all(p[1] >= 1.0 for p in r[7])]
good.sort(key=lambda r: -min(p[0] for p in r[7]))
print(f"\n== {TFH}ч: ≥+0.3R каждый год и ≥1 сделки/нед: {len(good)} ==")
for r in good[:20]:
    print(line(r))
