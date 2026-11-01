"""the header's yearly expectation by the strictest money (money_arm2.py: every ⚡ order hour by hour, the armed limits
holding room, the never-filled ones too, the bot's nearer-limit swap): ⚡ alone / + P/R, SMC, EMA / + HTF, a year from $100,
144 weekly windows, 3 seeds. usage: money_expect4.py [rule] -> <LABSTORE>/wf/money_expect4_<rule>.json"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
RULE = sys.argv[1] if len(sys.argv) > 1 else "A"; SEEDS = [1, 2, 3]
_D = {}
def _init(D): _D.update(D)
def job(a):
    k, sd, A = a
    OT = [v for v in _D["ot"] if v["mod"] in X.KINDS[k]]
    return k, sd, A, MA2.run(_D["or"], OT, A, A + 365 * 86400, RULE, sd)
if __name__ == "__main__":
    D = {"or": MA2.orders(), "ot": [v for v in M.build("base") if v["mod"] != "dlm"]}
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, [(k, sd, A) for k in X.KINDS for sd in SEEDS for A in X.STARTS + [X.LAST]], chunksize=6)
    R = {}
    for k, sd, A, r in res: R.setdefault((k, sd), {})[A] = r
    out = {}
    for k in X.KINDS:
        E = [np.array([R[(k, sd)][A][0] for A in X.STARTS]) for sd in SEEDS]
        out[k] = {"p10": int(np.mean([np.percentile(e, 10) for e in E])), "p50": int(np.mean([np.median(e) for e in E])), "p90": int(np.mean([np.percentile(e, 90) for e in E])),
                  "dd": int(round(np.mean([np.median([R[(k, sd)][A][1] for A in X.STARTS]) for sd in SEEDS]) * 100)), "last12": int(np.mean([R[(k, sd)][X.LAST][0] for sd in SEEDS])),
                  "liq_windows": int(np.mean([(np.array([R[(k, sd)][A][0] for A in X.STARTS]) <= 0).sum() for sd in SEEDS]))}
        print(RULE, k, out[k], flush=True)
    json.dump(out, open(f"{M.ST}/wf/money_expect4_{RULE.replace('|', '_').replace('=', '')}.json", "w"), indent=1)
