"""the header's yearly expectation with the bot's arming (money_arm.py: a ⚡ limit holds its risk from the moment it goes on
the exchange) and the room by the score over the stream's threshold (v0.99.752, rule "Bn"); ⚡ alone / + P/R, SMC, EMA /
+ HTF, 5 random orders averaged. usage: money_expect3.py [rule] -> the numbers for EXPECT_YEAR"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlm_exits as DX, money_multi as M, money_expect as X, money_arm as MA
from multiprocessing import Pool
RULE = sys.argv[1] if len(sys.argv) > 1 else "Bn"; SEEDS = [1, 2, 3, 4, 5]
_D = {}
def _init(D): _D.update(D)
def job(a):
    k, sd, A = a
    OT = [v for v in _D["ot"] if v["mod"] in X.KINDS[k]]
    v = MA.run_arm(_D["dl"], OT, A, A + 365 * 86400, RULE, sd)
    return k, sd, A, v
if __name__ == "__main__":
    st0 = json.load(open("/home/user/vp-poc-screener/vp_dlm_model.json"))["streams"][0]
    Pw = DX.walk(DX.pool_lv(), take=st0["take_atr"], soft=st0["stop_atr"], hard=st0["hard_stop_atr"])
    D = {"dl": MA.dlm_events(Pw), "ot": [v for v in M.build("base") if v["mod"] != "dlm"]}
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, [(k, sd, A) for k in X.KINDS for sd in SEEDS for A in X.STARTS + [X.LAST]], chunksize=12)
    R = {}
    for k, sd, A, r in res: R.setdefault((k, sd), {})[A] = r
    out = {}
    for k in X.KINDS:
        E = [np.array([R[(k, sd)][A][0] for A in X.STARTS]) for sd in SEEDS]
        out[k] = {"p10": int(np.mean([np.percentile(e, 10) for e in E])), "p50": int(np.mean([np.median(e) for e in E])), "p90": int(np.mean([np.percentile(e, 90) for e in E])),
                  "dd": int(round(np.mean([np.median([R[(k, sd)][A][2] for A in X.STARTS]) for sd in SEEDS]) * 100)), "last12": int(np.mean([R[(k, sd)][X.LAST][0] for sd in SEEDS]))}
        print(RULE, k, out[k], flush=True)
    json.dump(out, open(f"{M.ST}/wf/money_expect3_{RULE}.json", "w"), indent=1)
