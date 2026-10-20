import os, numpy as np, time
from common import D
STOPS = ("1", "1.5", "2", "sw"); EXITS = ("t1", "t2", "t3", "cas"); HOLDS = (24, 48)
F, Y = [], []
for f in sorted(os.listdir(f"{D}/cas")):
    z = np.load(f"{D}/cas/{f}"); F.append(z["F"]); Y.append(z["Y"])
F = np.concatenate(F); Y = np.concatenate(Y)
T, s, rng, prior, sopp, exc, mv, wid, b24, atrp = F.T
yr = np.array([time.gmtime(t).tm_year for t in T])
print("events", len(F))
V = {
 "all short": s < 0, "all long": s > 0,
 "S pump-fade (prior>=24, exc>=4)": (s < 0) & (prior >= 24) & (exc >= 4),
 "S pump-fade big (prior>=24, rng>=12)": (s < 0) & (prior >= 24) & (rng >= 12),
 "S reject (up-cross <=6 bars ago)": (s < 0) & (sopp <= 6),
 "S reject <=12, exc>=2": (s < 0) & (sopp <= 12) & (exc >= 2),
 "L dump-recover (prior>=24, exc>=4)": (s > 0) & (prior >= 24) & (exc >= 4),
 "L reject (dn-cross <=6)": (s > 0) & (sopp <= 6),
}
def cell(m, si, xi, hi):
    y = Y[m, si, xi, hi]; y = y[~np.isnan(y)]
    return y.mean() if len(y) else np.nan, (y > 0).mean() if len(y) else np.nan, len(y)
for name, m in V.items():
    print(f"\n== {name}  n={m.sum()}")
    best = []
    for si in range(4):
        for xi in range(4):
            for hi in range(2):
                mu, wr, n = cell(m, si, xi, hi); best.append((mu, si, xi, hi, wr, n))
    best.sort(reverse=True)
    for mu, si, xi, hi, wr, n in best[:4]:
        yrs = " ".join(f"{y}:{np.nanmean(Y[m & (yr == y), si, xi, hi]):+.2f}" for y in range(2020, 2027) if (m & (yr == y)).sum() > 50)
        print(f"  stop {STOPS[si]:>3} {EXITS[xi]:>3} {HOLDS[hi]}h  R {mu:+.3f} wr {wr:.0%} n {n}  | {yrs}")
