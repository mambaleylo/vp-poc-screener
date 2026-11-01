"""0.3 ATR arming / 20x vs the bot's 0.6 / 14x on the strictest money, by the windows' start year (2023 / 2024 / 2025),
a year from $100, 2 seeds: the median, the bad 10%, the drawdown, the windows better than the bot's -> the table"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
F = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0"
RULES = {"сейчас (0.6 ATR, 14x)": F, "0.3 ATR": F.replace("arm=0.6", "arm=0.3"), "0.45 ATR": F.replace("arm=0.6", "arm=0.45"),
         "20x": F + "|cap=20", "0.3 ATR + 20x": F.replace("arm=0.6", "arm=0.3") + "|cap=20"}
if len(sys.argv) > 1 and sys.argv[-1] == "lev":
    RULES = {"сейчас (14x)": F, "16x": F + "|cap=16", "17x": F + "|cap=17", "18x": F + "|cap=18", "20x": F + "|cap=20"}
SEEDS = [1, 2]
_D = {}
def _init(D): _D.update(D)
def job(a):
    nm, sd, A = a
    return nm, sd, A, MA2.run(_D["or"], _D["ot"], A, A + 365 * 86400, RULES[nm], sd)
if __name__ == "__main__":
    D = {"or": MA2.orders(), "ot": [v for v in M.build("base") if v["mod"] != "dlm"]}
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, [(nm, sd, A) for nm in RULES for sd in SEEDS for A in X.STARTS], chunksize=6)
    R = {}
    for nm, sd, A, v in res: R.setdefault(nm, {}).setdefault(A, []).append(v)
    base = list(RULES)[0]
    for yr in (2023, 2024, 2025):
        W = [A for A in X.STARTS if M.ts(yr) <= A < M.ts(yr + 1)]
        print(f"старт в {yr} ({len(W)} окон):", flush=True)
        for nm in RULES:
            E = np.array([np.mean([x[0] for x in R[nm][A]]) for A in W]); dd = np.array([np.mean([x[1] for x in R[nm][A]]) for A in W])
            b = np.array([np.mean([x[0] for x in R[base][A]]) for A in W])
            print(f"   {nm:22s} плохой ${np.percentile(E, 10):>7,.0f} обычный ${np.median(E):>8,.0f} просадка {np.median(dd)*100:.0f}% | лучше нынешнего в {int((E > b * 1.001).sum())}/{len(W)}", flush=True)
    print("deep done", flush=True)
