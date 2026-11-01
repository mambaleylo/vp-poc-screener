"""⚡'s near misses on an account of their own (the user: "если отдельный депозит завести под это дело, или лучше этот
депозит потратить на основную связку?"): the module alone ($100, its own open-risk cap 100%, the coin's maximum leverage)
at 2 / 3 / 4.5%, against the main bundle on the same $100; and the two accounts together ($100 + $100) against the bundle
on $200 (= 2 x $100: every rule is a share of the account), window by window -> the table"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X, money_params as MP
from multiprocessing import Pool
F = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125"; SEEDS = (1, 2)
VARS = {"основная связка": ("main", None), "≤0.3 ATR отдельно, риск 2%": ("near0.3", 2.0), "≤0.3 ATR отдельно, риск 3%": ("near0.3", 3.0),
        "≤0.3 ATR отдельно, риск 4.5%": ("near0.3", 4.5), "≤0.2 ATR отдельно, риск 3%": ("near0.2", 3.0), "≤0.2 ATR отдельно, риск 4.5%": ("near0.2", 4.5)}
_D = {}
def _init(D): _D.update(D)
def job(a):
    v, sd, A = a
    k, rk = VARS[v]
    if k == "main":
        return v, sd, A, MA2.run(_D["or"], _D["ot"], A, A + 365 * 86400, F, sd)
    return v, sd, A, MA2.run([], _D[k], A, A + 365 * 86400, F, sd, rk=dict(MP.rk(emx=3.0), dlm=0.0, dmiss=rk))
if __name__ == "__main__":
    D = {"or": MA2.orders(), "ot": [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]}
    for k in ("near0.2", "near0.3"):
        D[k] = [dict(v, r=v["r"] - 0.03) for v in json.load(open(f"{M.ST}/wf/dlm_miss_{k}.json")) if v["sym"]]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, [(v, sd, A) for v in VARS for sd in SEEDS for A in X.STARTS], chunksize=8)
    R = {}
    for v, sd, A, x in res: R.setdefault(v, {}).setdefault(A, []).append(x)
    E = {v: np.array([np.mean([x[0] for x in R[v][A]]) for A in X.STARTS]) for v in VARS}
    DD = {v: np.array([np.mean([x[1] for x in R[v][A]]) for A in X.STARTS]) for v in VARS}
    m = E["основная связка"]
    print("один счёт $100 | обычный год | плохой год | хороший | просадка медиана | в плохом окне", flush=True)
    for v in VARS:
        print(f"{v} | ${np.median(E[v]):,.0f} | ${np.percentile(E[v], 10):,.0f} | ${np.percentile(E[v], 90):,.0f} | {np.median(DD[v]) * 100:.0f}% | {np.percentile(DD[v], 90) * 100:.0f}%", flush=True)
    print("два счёта ($100 связка + $100 модуль) против связки на $200 | обычный год | плохой год | лучше в окнах | корреляция окон", flush=True)
    print(f"связка на $200 | ${np.median(2 * m):,.0f} | ${np.percentile(2 * m, 10):,.0f} | — | —", flush=True)
    for v in list(VARS)[1:]:
        s = m + E[v]
        print(f"связка + {v} | ${np.median(s):,.0f} | ${np.percentile(s, 10):,.0f} | {int((s > 2 * m * 1.001).sum())}/{len(m)} | {np.corrcoef(np.log(m + 1), np.log(E[v] + 1))[0, 1]:.2f}", flush=True)
    print("money miss2 done", flush=True)
