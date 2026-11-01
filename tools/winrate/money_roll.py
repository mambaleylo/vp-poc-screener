"""the strictest money (money_arm2.run, the bot's settings: every ⚡ order holds room, the coin's maximum leverage, 144 windows
x 2 seeds) for ⚡ close2h scored three ways, wick4h and the other modules the same: lab = the lab's bot-feature yearly models
(the money runs until now), rsY = the restored research engine's models once a year (the bot's way), rsM0 = the same retrained
every month (dlm_allorders_rs.py)"""
import sys, os, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
F = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125"; SEEDS = (1, 2)
VARS = {"lab (как считали до сих пор)": "", "исследование, раз в год (как бот)": "_rsY", "исследование, каждый месяц": "_rsM0"}
_D = {}
def _init(D): _D.update(D)
def job(a):
    v, sd, A = a
    return v, sd, A, MA2.run(_D[v], _D["ot"], A, A + 365 * 86400, F, sd)
if __name__ == "__main__":
    D = {"ot": [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]}
    for v, suf in VARS.items():
        D[v] = MA2.orders(suf)
        c2 = [o for o in D[v] if o["stream"] == "close2h" and o["filled"]]
        print(f"{v}: ордеров ⚡ {len(D[v])}, close2h исполнено {len(c2)}, R {np.mean([o['r'] for o in c2]):+.3f}", flush=True)
    jobs = [(v, sd, A) for v in VARS for sd in SEEDS for A in X.STARTS]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, jobs, chunksize=8)
    R = {}
    for v, sd, A, x in res: R.setdefault(v, {}).setdefault(A, []).append(x)
    b = np.array([np.mean([x[0] for x in R["исследование, раз в год (как бот)"][A]]) for A in X.STARTS])
    print("вариант | обычный год | плохой год (1 из 10) | просадка медиана | в плохом окне | лучше «как бот»", flush=True)
    for v in VARS:
        E = np.array([np.mean([x[0] for x in R[v][A]]) for A in X.STARTS]); dd = np.array([np.mean([x[1] for x in R[v][A]]) for A in X.STARTS])
        print(f"{v} | ${np.median(E):,.0f} | ${np.percentile(E, 10):,.0f} | {np.median(dd) * 100:.0f}% | {np.percentile(dd, 90) * 100:.0f}% | {int((E > b * 1.001).sum())}/{len(b)}", flush=True)
    print("money roll done", flush=True)
