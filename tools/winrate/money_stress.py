"""a module's risk under stress: its trades X R worse than the backtest list (the selection bias / friction) — is a
higher risk still better? money_params.py's money. usage: money_stress.py emx 2,3,4 0,0.2,0.35"""
import sys, os, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import money_multi as M, money_expect as X, money_osc as O, money_params as MP
from multiprocessing import Pool
MOD = sys.argv[1]; RISKS = [float(x) for x in sys.argv[2].split(",")]; HAIR = [float(x) for x in sys.argv[3].split(",")]
def job(a):
    h, r, A = a
    key = ("b", h)
    if key not in M._EV:
        M._EV[key] = [dict(v, r=v["r"] - h) if v["mod"] == MOD else v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"]]
    return h, r, A, M.run(M._EV[key], A, A + 365 * 86400, 14.0, O.W_OSC, eq0=100.0, rk_=MP.rk(**{MOD: r}))
if __name__ == "__main__":
    with Pool(4) as P:
        res = P.map(job, [(h, r, A) for h in HAIR for r in RISKS for A in X.STARTS], chunksize=6)
    R = {}
    for h, r, A, x in res: R.setdefault((h, r), {})[A] = x
    for h in HAIR:
        b0 = np.array([R[(h, RISKS[0])][A][0] for A in X.STARTS])
        for r in RISKS:
            E = np.array([R[(h, r)][A][0] for A in X.STARTS]); dd = np.array([R[(h, r)][A][3] for A in X.STARTS])
            print(f"{MOD} хуже на {h:.2f}R, риск {r}%: плохой ${np.percentile(E,10):,.0f} обычный ${np.median(E):,.0f} просадка {np.median(dd)*100:.0f}%/{dd.max()*100:.0f}% | к {RISKS[0]}%: лучше в {int((E > b0*1.001).sum())}/144 x{np.median(E/b0):.2f}", flush=True)
