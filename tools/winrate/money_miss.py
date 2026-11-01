"""⚡'s near misses as a module (dlm_miss.py: the price within d ATR of a never-touched limit -> the market entry at the next
hour, the ⚡ exits) in the bundle by the strictest money (the bot's settings, the coin's maximum leverage), its risk 1-3%,
144 windows x 2 seeds -> the table"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X, money_params as MP
from multiprocessing import Pool
F = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125"; SEEDS = (1, 2)
VARS = {"сейчас": (None, 0.0), "≤0.2 ATR, риск 1%": ("near0.2", 1.0), "≤0.2 ATR, риск 2%": ("near0.2", 2.0),
        "≤0.3 ATR, риск 1%": ("near0.3", 1.0), "≤0.3 ATR, риск 2%": ("near0.3", 2.0), "≤0.3 ATR, риск 3%": ("near0.3", 3.0),
        "≤0.1 ATR, риск 2%": ("near0.1", 2.0)}
_D = {}
def _init(D): _D.update(D)
def job(a):
    v, sd, A = a
    k, rk = VARS[v]
    OT = _D["ot"] + (_D[k] if k else [])
    return v, sd, A, MA2.run(_D["or"], sorted(OT, key=lambda x: x["t0"]), A, A + 365 * 86400, F, sd, rk=dict(MP.rk(emx=3.0), dmiss=rk))
if __name__ == "__main__":
    D = {"or": MA2.orders(), "ot": [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]}
    for k in ("near0.1", "near0.2", "near0.3"):
        D[k] = [dict(v, r=v["r"] - 0.03) for v in json.load(open(f"{M.ST}/wf/dlm_miss_{k}.json")) if v["sym"]]   # the friction as the others'
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, [(v, sd, A) for v in VARS for sd in SEEDS for A in X.STARTS], chunksize=8)
    R = {}
    for v, sd, A, x in res: R.setdefault(v, {}).setdefault(A, []).append(x)
    b = np.array([np.mean([x[0] for x in R["сейчас"][A]]) for A in X.STARTS])
    print("вариант | обычный год | плохой год | просадка медиана | в плохом окне | лучше нынешнего | по годам старта 2023 / 2024 / 2025", flush=True)
    for v in VARS:
        E = np.array([np.mean([x[0] for x in R[v][A]]) for A in X.STARTS]); dd = np.array([np.mean([x[1] for x in R[v][A]]) for A in X.STARTS])
        yrs = [np.median([E[i] for i, A in enumerate(X.STARTS) if M.ts(y) <= A < M.ts(y + 1)]) for y in (2023, 2024, 2025)]
        print(f"{v} | ${np.median(E):,.0f} | ${np.percentile(E, 10):,.0f} | {np.median(dd) * 100:.0f}% | {np.percentile(dd, 90) * 100:.0f}% | {int((E > b * 1.001).sum())}/{len(b)} | "
              + " / ".join(f"${y_:,.0f}" for y_ in yrs), flush=True)
    print("money miss done", flush=True)
