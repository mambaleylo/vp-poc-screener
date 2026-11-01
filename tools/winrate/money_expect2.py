"""the header's yearly expectation with the ⚡ trades of an hour in a random order (5 orders, averaged — money_order.py):
⚡ alone / + P/R, SMC, EMA / + HTF, the bot's settings (14x, the 2h shorts x0.5, WaveTrend x1.25 at <= -33, EMA 3%, the cap
95%), for ⚡'s exits given as argv (soft/take, default the model's). -> the numbers for EXPECT_YEAR"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlm_exits as DX, money_multi as M, money_expect as X, money_osc as O, money_params as MP, money_order as MOR
from multiprocessing import Pool
SOFT, TAKE = (float(x) for x in (sys.argv[1] if len(sys.argv) > 1 else "2.0/1.1").split("/"))
SEEDS = [1, 2, 3, 4, 5]
_E = {}
def _init(E): _E.update(E)
def job(a):
    k, sd, A = a
    EV = [v for v in _E[sd] if v["mod"] in X.KINDS[k]]
    return k, sd, A, M.run(EV, A, A + 365 * 86400, 14.0, O.W_OSC, eq0=100.0, heat=0.95, rk_=MP.rk(emx=3.0))
if __name__ == "__main__":
    Pw = DX.walk(DX.pool_lv(), soft=SOFT, take=TAKE); E = {sd: MOR.events(Pw, sd) for sd in SEEDS}
    with Pool(4, initializer=_init, initargs=(E,)) as Pl:
        res = Pl.map(job, [(k, sd, A) for k in X.KINDS for sd in SEEDS for A in X.STARTS + [X.LAST]], chunksize=12)
    R = {}
    for k, sd, A, r in res: R.setdefault((k, sd), {})[A] = r
    out = {}
    for k in X.KINDS:
        E_ = [np.array([R[(k, sd)][A][0] for A in X.STARTS]) for sd in SEEDS]
        out[k] = {"p10": int(np.mean([np.percentile(e, 10) for e in E_])), "p50": int(np.mean([np.median(e) for e in E_])),
                  "p90": int(np.mean([np.percentile(e, 90) for e in E_])),
                  "dd": int(round(np.mean([np.median([R[(k, sd)][A][3] for A in X.STARTS]) for sd in SEEDS]) * 100)),
                  "last12": int(np.mean([R[(k, sd)][X.LAST][0] for sd in SEEDS]))}
        print(k, out[k], flush=True)
    json.dump(out, open(f"{M.ST}/wf/money_expect2_{SOFT}_{TAKE}.json", "w"), indent=1)
