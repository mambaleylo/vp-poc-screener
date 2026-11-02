"""the user: "если первые полгода пополнять баланс на 100 долларов каждый месяц, как вырастет баланс за год?" — the header's
strictest money (money_expect4.py: the bundle + HTF, every ⚡ order hour by hour, the header's rule) from $100 alone vs $100 +
$100 every 30 days 6 times ($700 in): the year's end and the balance month by month (the median, the bad 1-in-10 and the
good 1-in-10 of the 144 weekly windows 2023-02..2025-10, the mean of the seeds), the last 12 months (Nov 2025 .. Oct 2026).
usage: ALLSUF=_clr money_dep.py [rule] [seeds] -> <LABSTORE>/wf/money_dep.json"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
RULE = ARGV[0] if ARGV else "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125"; SEEDS = [int(x) for x in (ARGV[1] if len(ARGV) > 1 else "1,2").split(",")]
VARS = {"только $100 на старте": "|path=1", "$100 + по $100 каждый месяц 6 раз ($700)": "|path=1|dep=100/30/6"}
_D = {}
def _init(D): _D.update(D)
def job(a):
    v, sd, A = a
    return v, sd, A, MA2.run(_D["or"], _D["ot"], A, A + 365 * 86400, RULE + VARS[v], sd)
if __name__ == "__main__":
    D = {"or": MA2.orders(), "ot": [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]}
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, [(v, sd, A) for v in VARS for sd in SEEDS for A in X.STARTS + [X.LAST]], chunksize=6)
    R = {}
    for v, sd, A, r in res: R.setdefault((v, sd), {})[A] = r
    out = {}
    for v in VARS:
        P = [np.array([R[(v, sd)][A][4] for A in X.STARTS]) for sd in SEEDS]   # seeds x windows x 13
        q = lambda f: [int(round(np.mean([f(p[:, m]) for p in P]))) for m in range(13)]
        o = {"p10": q(lambda x: np.percentile(x, 10)), "p50": q(np.median), "p90": q(lambda x: np.percentile(x, 90)),
             "dd": int(round(np.mean([np.median([R[(v, sd)][A][1] for A in X.STARTS]) for sd in SEEDS]) * 100)),
             "dd90": int(round(np.mean([np.percentile([R[(v, sd)][A][1] for A in X.STARTS], 90) for sd in SEEDS]) * 100)),
             "liq": float(np.mean([sum(R[(v, sd)][A][0] <= 0 for A in X.STARTS) for sd in SEEDS])),
             "last12": [int(round(np.mean([R[(v, sd)][X.LAST][4][m] for sd in SEEDS]))) for m in range(13)]}
        out[v] = o
        print(f"\n{v}: конец года плохой ${o['p10'][-1]:,} · обычный ${o['p50'][-1]:,} · хороший ${o['p90'][-1]:,}; "
              f"просадка медиана {o['dd']}% (плохое окно {o['dd90']}%), обнулений {o['liq']:.1f}/{len(X.STARTS)}; последние 12 мес ${o['last12'][-1]:,}", flush=True)
        print("месяц | плохой | обычный | хороший | последние 12 мес", flush=True)
        for m in range(13):
            print(f"{m + 1 if m < 12 else 'итог'} | ${o['p10'][m]:,} | ${o['p50'][m]:,} | ${o['p90'][m]:,} | ${o['last12'][m]:,}", flush=True)
    json.dump(out, open(f"{M.ST}/wf/money_dep.json", "w"), indent=1)
    print("money dep done", flush=True)
