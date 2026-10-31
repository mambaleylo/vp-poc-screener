"""money_multi.py, the leverage cap grid with the 2h-stream shorts at x0.5. usage: money_multi3.py 12 13 14 16 17 18"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import money_multi as M
CAPS = [float(x) for x in sys.argv[1:]] or [12.0, 13.0, 14.0, 16.0, 17.0, 18.0]
M.VARIANTS = [(f"{c:.0f}x, 2ч-шорты x0.5", "base", c, "W2S") for c in CAPS]
from multiprocessing import Pool
if __name__ == "__main__":
    jobs = [(nm, pool, cap, wfn, A) for nm, pool, cap, wfn in M.VARIANTS for A in M.STARTS]
    with Pool(4) as P:
        res = P.map(M.job, jobs, chunksize=1)
    prev = json.load(open(os.path.join(M.ST, "wf", "money_multi.json")))
    for nm, A, r in res: prev.setdefault(nm, {})[str(A)] = r
    json.dump(prev, open(os.path.join(M.ST, "wf", "money_multi.json"), "w"))
    base = prev["10x, монеты бота"]
    key = lambda nm: (int(nm.split("x")[0]) if nm.split("x")[0].isdigit() else 999, nm)
    for nm in sorted(prev, key=key):
        v = prev[nm]
        E = np.array([v[str(A)][0] for A in M.STARTS]); dd = np.array([v[str(A)][3] for A in M.STARTS])
        q = E / np.array([base[str(A)][0] for A in M.STARTS])
        print(f"{nm:26s} медиана ${np.median(E):>9,.0f} худший ${E.min():>7,.0f} 2-й худший ${np.sort(E)[1]:>7,.0f} лучший ${E.max():>9,.0f} | просадка медиана {np.median(dd)*100:.0f}% худшая {dd.max()*100:.0f}% | к 10x: лучше в {int((q > 1.001).sum())}/12, медиана x{np.median(q):.2f}", flush=True)
