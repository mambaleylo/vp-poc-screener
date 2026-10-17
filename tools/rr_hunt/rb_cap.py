"""daily range breakout with a cap on positions open at once per side: random order among same-day signals
(20 shuffles) to see how much the result depends on which signals got the free slots"""
import glob, pickle, numpy as np
from mk import ts
import rb_daily as R
ev = []
for k, fn in enumerate(sorted(glob.glob("rb/*.pkl"))):
    for t, s, f, y in pickle.load(open(fn, "rb")):
        ev.append((t, k, s, f, y))
T = np.array([e[0] for e in ev]); SY = np.array([e[1] for e in ev]); SD = np.array([e[2] for e in ev])
NN = np.array([e[3]["N"] for e in ev]); RG = np.array([e[3]["rg"] for e in ev]); BRK = np.array([e[3]["brk"] for e in ev])
OWN = np.array([bool(e[3]["own200"]) for e in ev]); WEEK = np.array([bool(e[3]["week"]) for e in ev])
Y = np.stack([e[4] for e in ev])
YRS = (2021, 2022, 2023, 2024, 2025)
YM = {y: (T >= ts(y)) & (T < (ts(y + 1) if y < 2025 else ts(2027))) for y in YRS}
WK = {y: ((ts(y + 1) if y < 2025 else ts(2026, 10)) - ts(y)) / (7 * 86400) for y in YRS}
def replay(idx, r, j, cap, rng):
    pri = rng.random(len(idx))
    o = idx[np.lexsort((pri, T[idx]))]
    busy, act, out = {}, [], []
    for i in o:
        key = (SY[i], SD[i]); t = T[i]
        if busy.get(key, 0) > t or r[i] != r[i]:
            continue
        act = [a for a in act if a[0] > t]
        if cap and sum(1 for a in act if a[1] == SD[i]) >= cap:
            continue
        end = t + int(j[i]) * 86400
        busy[key] = end; act.append((end, SD[i])); out.append((end, float(r[i])))
    return out
CONF = []
for N in (15, 20, 30):
    for K in (2.5, 3.0, 4.0):
        for g in ("own200", "own200+week"):
            for sk in (1.5, 2.0):
                for xn in ("dc20", "dc10", "ch8"):
                    CONF.append((N, K, g, sk, xn))
out_rows = []
for cap in (6, 12):
    for N, K, g, sk, xn in CONF:
        m0 = (NN == N) & (RG < K) & (OWN if g == "own200" else (OWN & WEEK))
        si, xi = R.STOPS.index(sk), R.EXITS.index(xn)
        r = Y[:, si, xi, 0].astype(float); j = Y[:, si, xi, 1]
        per = []
        for y in YRS:
            idx = np.where(m0 & YM[y])[0]
            av, nn = [], []
            for seed in range(20):
                o = replay(idx, r, j, cap, np.random.default_rng(seed))
                rs = np.array([x[1] for x in o]); av.append(rs.mean() if len(rs) else np.nan); nn.append(len(rs))
            per.append((np.nanmean(av), np.nanmin(av), np.nanmax(av), np.mean(nn) / WK[y]))
        tr = min(p[0] for p in per[:3])
        out_rows.append((tr, cap, N, K, g, sk, xn, per))
out_rows.sort(key=lambda r: -r[0])
print("== лимит одновременных сделок; среднее по 20 перемешиваниям (мин…макс); выбор по 2021–23 ==")
for tr, cap, N, K, g, sk, xn, per in out_rows[:30]:
    print(f"лимит {cap:2d} N{N} <{K} {g:11s} стоп {sk} {xn:4s} || " + " | ".join(f"{y}: {p[0]:+.2f} ({p[1]:+.2f}…{p[2]:+.2f})R×{p[3]:.1f}" for y, p in zip(YRS, per)), flush=True)
pickle.dump(out_rows, open("rb_cap.pkl", "wb"))
