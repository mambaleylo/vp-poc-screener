"""money_multi.py, more variants: 10x / 15x with the 2h-stream shorts at x0.5"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import money_multi as M
M.VARIANTS = [("10x, 2ч-шорты x0.5", "base", 10.0, "W2S"), ("15x, монеты бота", "base", 15.0, None), ("15x, 2ч-шорты x0.5", "base", 15.0, "W2S")]
from multiprocessing import Pool
if __name__ == "__main__":
    prev = json.load(open(os.path.join(M.ST, "wf", "money_multi.json")))
    jobs = [(nm, pool, cap, wfn, A) for nm, pool, cap, wfn in M.VARIANTS for A in M.STARTS]
    with Pool(4) as P:
        res = P.map(M.job, jobs, chunksize=1)
    for nm, A, r in res: prev.setdefault(nm, {})[str(A)] = r
    json.dump(prev, open(os.path.join(M.ST, "wf", "money_multi.json"), "w"))
    base = prev["10x, монеты бота"]
    for nm, v in prev.items():
        E = np.array([v[str(A)][0] for A in M.STARTS]); dd = np.array([v[str(A)][3] for A in M.STARTS])
        q = E / np.array([base[str(A)][0] for A in M.STARTS])
        print(f"{nm:26s} медиана ${np.median(E):>9,.0f} худший ${E.min():>7,.0f} 2-й худший ${np.sort(E)[1]:>7,.0f} лучший ${E.max():>9,.0f} | просадка медиана {np.median(dd)*100:.0f}% худшая {dd.max()*100:.0f}% | к 10x: лучше в {int((q > 1.001).sum())}/12, медиана x{np.median(q):.2f}", flush=True)
