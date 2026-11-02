"""⚡ 4h the same check as 2h (money_roll.py): the bot's wick4h orders scored by the research-engine models (s23 w1 E0, as the
deployed one was trained) vs the lab's bot-feature models, each stream crossed: which pair makes the most money (the strictest
money, 144 windows x 2 seeds). The combos are links in <LABSTORE>/wf: _c<wick><close> with l = the lab, r = the research yearly."""
import sys, os, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
F = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125"; SEEDS = (1, 2); W = f"{M.ST}/wf"
SRC = {("wick4h", "l"): "allorders_wick4h.npz", ("wick4h", "r"): "allorders_wick4h_rsY.npz", ("close2h", "l"): "allorders_close2h.npz", ("close2h", "r"): "allorders_close2h_rsY.npz", ("wick4h", "d"): "allorders_wick4h_dep.npz", ("close2h", "d"): "allorders_close2h_dep.npz"}
VARS = {"бот как есть (деревья из vp_dlm_model)": "dd", "4ч бот + 2ч лаб": "dl", "4ч лаб + 2ч бот": "ld", "4ч лаб + 2ч лаб": "ll", "4ч как бот + 2ч как бот": "rr", "4ч лаб + 2ч как бот": "lr", "4ч как бот + 2ч лаб": "rl"}
for c in VARS.values():
    for st, k in (("wick4h", c[0]), ("close2h", c[1])):
        dst = f"{W}/allorders_{st}_c{c}.npz"
        if os.path.lexists(dst): os.remove(dst)
        os.symlink(SRC[(st, k)], dst)
_D = {}
def _init(D): _D.update(D)
def job(a):
    v, sd, A = a
    return v, sd, A, MA2.run(_D[v], _D["ot"], A, A + 365 * 86400, F, sd)
if __name__ == "__main__":
    D = {"ot": [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]}
    for v, c in VARS.items():
        D[v] = MA2.orders(f"_c{c}")
        for st in ("wick4h", "close2h"):
            f = [o for o in D[v] if o["stream"] == st and o["filled"]]
            print(f"{v}: {st} исполнено {len(f)}, R {np.mean([o['r'] for o in f]):+.3f}", flush=True)
    jobs = [(v, sd, A) for v in VARS for sd in SEEDS for A in X.STARTS]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, jobs, chunksize=8)
    R = {}
    for v, sd, A, x in res: R.setdefault(v, {}).setdefault(A, []).append(x)
    b = np.array([np.mean([x[0] for x in R["бот как есть (деревья из vp_dlm_model)"][A]]) for A in X.STARTS])
    print("вариант | обычный год | плохой год (1 из 10) | просадка медиана | в плохом окне | лучше «бот как есть»", flush=True)
    for v in VARS:
        E = np.array([np.mean([x[0] for x in R[v][A]]) for A in X.STARTS]); dd = np.array([np.mean([x[1] for x in R[v][A]]) for A in X.STARTS])
        print(f"{v} | ${np.median(E):,.0f} | ${np.percentile(E, 10):,.0f} | {np.median(dd) * 100:.0f}% | {np.percentile(dd, 90) * 100:.0f}% | {int((E > b * 1.001).sum())}/{len(b)}", flush=True)
    print("money 4h done", flush=True)
