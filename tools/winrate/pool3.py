import numpy as np, pickle, warnings; warnings.filterwarnings("ignore")
import pool as PL
from mk import ts
X = pickle.load(open("pool_x.pkl", "rb"))
def rows_of(sel, part):
    a = [r for nm in sel for r in PL.P[nm] if part == "all" or r[4] == "check"]
    return a + [r for nm in sel for r in X[nm]]
def fixed(rows, mode, shift, t_start):
    rows = sorted(rows); t0 = np.array([r[0] for r in rows], float); t1 = np.array([r[1] for r in rows], float)
    R = np.array([r[2] for r in rows]); ST = np.array([r[3] for r in rows]); i = int(np.searchsorted(t0, t_start))
    mp, rf, lad, _ = mode
    return PL.multi(t0, t1, R, ST, i, t_start + 365 * 86400.0, mp, rf, lad, shift)
SETS = {"пул 4 потока": ['1ч 2×ATR28 т1.5', '4ч тень т1', '30м 2×ATR28 т1', '2ч 2ATR т1'], "4ч тень т1": ['4ч тень т1'], "4ч+2ч": ['4ч тень т1', '2ч 2ATR т1'],
        "4ч+1ч": ['4ч тень т1', '1ч 2×ATR28 т1.5'], "4ч т1 + 4ч т0.5": ['4ч тень т1', '4ч тень т0.5']}
for nm in PL.SPEC:
    if X.get(nm) is None: continue
    a = [r for r in PL.P[nm] if r[4] == "check"] + X[nm]
    t = np.array([r[0] for r in a]); R = np.array([r[2] for r in a]); W = np.array([r[5] for r in a])
    ys = []
    for Y in range(2022, 2027):
        m = (t >= ts(Y)) & (t < ts(Y + 1)); ys.append(f"{Y}: {R[m].mean():+.3f}R WR{W[m].mean()*100:.0f}% n{m.sum()}")
    h = t >= ts(2025, 10)
    print(f"{nm:18s} невиданные | " + " | ".join(ys) + f" || посл. 12 мес {R[h].mean():+.3f}R WR{W[h].mean()*100:.0f}% n{h.sum()}")
print()
MODES = PL.MODES + [(12, 0.05, False, "до 12 по 5%")]
for sn, sel in SETS.items():
    for part in ("unseen", "all"):
        rr = rows_of(sel, part)
        for md in MODES:
            out = []
            for st in ((2022, 1), (2023, 1), (2024, 1), (2025, 1), (2025, 10)):
                out.append(f"{st[0]}.{st[1]:02d}: ${fixed(rr, md, -0.025, ts(*st)):6.0f}")
            print(f"{sn:16s} {part:6s} {md[3]:14s} осторожно, старт $100 → " + " | ".join(out), flush=True)
    print()
