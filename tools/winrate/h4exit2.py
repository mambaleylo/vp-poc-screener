import numpy as np, pickle, warnings; warnings.filterwarnings("ignore")
import pool as PL
from mk import ts
res = pickle.load(open("h4exit.pkl", "rb"))
roll = np.arange(ts(2024), ts(2025, 10) + 1, 7 * 86400.0)
for k in [(2.0, 1.0, 32), (2.0, 1.0, 48), (2.0, 1.25, 32), (2.0, 1.25, 48), (2.0, 0.75, 32), (1.5, 1.0, 32), (1.5, 1.0, 48), (1.5, 1.25, 48), (2.5, 1.0, 32), (2.5, 1.25, 32), (2.5, 1.5, 48), (3.0, 1.0, 32), (3.0, 1.5, 48)]:
    rows = sorted(res[k]); t0 = np.array([r[0] for r in rows], float); t1 = np.array([r[1] for r in rows], float)
    R = np.array([r[2] for r in rows]); ST = np.array([r[3] for r in rows]); W = np.array([r[5] for r in rows])
    un = np.array([r[4] != "train" for r in rows]); h = t0 >= ts(2025, 10)
    out = []
    for rk in (0.03, 0.04):
        o = np.array([PL.multi(t0, t1, R, ST, int(np.searchsorted(t0, s)), s + 365 * 86400.0, 20, rk, False, -0.025) for s in roll]) + 100
        o6 = np.array([PL.multi(t0, t1, R, ST, int(np.searchsorted(t0, s)), s + 182 * 86400.0, 20, rk, False, -0.025) for s in roll]) + 100
        last = PL.multi(t0, t1, R, ST, int(np.searchsorted(t0, ts(2025, 10))), ts(2025, 10) + 365 * 86400.0, 20, rk, False, -0.025) + 100
        out.append(f"{rk*100:.0f}%: посл.12м ${last:,.0f} | год медиана ${np.median(o):,.0f} хуже-10% ${np.percentile(o,10):,.0f} | 6м медиана ${np.median(o6):,.0f} ниже$100 {np.mean(o6<100)*100:.0f}%")
    print(f"стоп {k[0]} тейк {k[1]} держ {k[2]} | невид WR{W[un].mean()*100:.0f}% {R[un].mean():+.3f}R посл12м {R[un&h].mean():+.3f}R || " + " || ".join(out), flush=True)
