"""the fair yardstick for a filter that lowers the drawdown: every module's risk x k (money_arm2's "k=") on the same orders —
the money at the same drawdown. usage: ALLSUF=_clr money_k.py "0.6,0.7,0.8" -> the table"""
import sys, os, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
RULE = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125"; KS = [float(x) for x in (ARGV[0] if ARGV else "0.6,0.7,0.8").split(",")]
_D = {}
def _init(D): _D.update(D)
def job(a):
    k, A = a
    return k, A, MA2.run(_D["or"], _D["ot"], A, A + 365 * 86400, RULE + f"|k={k}", 1)
if __name__ == "__main__":
    D = {"or": MA2.orders(), "ot": [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]}
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, [(k, A) for k in KS for A in X.STARTS + [X.LAST]], chunksize=4)
    R = {(k, A): r for k, A, r in res}
    print("риск всех модулей × k | обычный год | плохой | хороший | просадка медиана | последние 12 мес", flush=True)
    for k in KS:
        e = np.array([R[(k, A)][0] for A in X.STARTS]); dd = np.array([R[(k, A)][1] for A in X.STARTS])
        print(f"×{k} | ${np.median(e):,.0f} | ${np.percentile(e, 10):,.0f} | ${np.percentile(e, 90):,.0f} | {np.median(dd) * 100:.0f}% | ${R[(k, X.LAST)][0]:,.0f}", flush=True)
    print("money k done", flush=True)
