"""SMC / HTF on the new coins in the money: the bundle (the strictest money, the bot's settings at 17x) with the bot's lists
as they are vs + the new coins' SMC / HTF trades of 2026 (lv_new.py: the deployed models, out of sample), at their
modules' risks; 6-month windows from $100 started every 2 weeks Jan..Apr 2026, 3 seeds -> the table"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import money_arm2 as MA2, money_multi as M
from multiprocessing import Pool
F = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=17"
W = [(A, A + 182 * 86400) for A in range(M.ts(2026, 1), M.ts(2026, 4, 20), 14 * 86400)]
SEEDS = [1, 2, 3]
def extra(mod):
    out = []
    for e in json.load(open(f"{M.ST}/wf/lv_new_{mod}.json")):
        if e["grp"] != "new": continue
        risk = e["lv"] * e["datr"] / 100; st = risk / e["lv"]
        out.append({"t0": e["t"] + 3600, "t1": e["tout"], "r": e["R"] - 0.03, "st": st, "sth": st * e["hard"], "mod": mod, "sym": e["coin"],
                    "side": e["side"], "e": e["lv"], "stream": None})
    return out
_D = {}
def _init(D): _D.update(D)
def job(a):
    nm, sd, (A, B) = a
    return nm, sd, A, MA2.run(_D["or"], _D[nm], A, B, F, sd)
if __name__ == "__main__":
    OT = [v for v in M.build("base") if v["mod"] != "dlm"]
    D = {"or": MA2.orders(), "как сейчас": OT, "+ новые монеты SMC": OT + extra("smc"), "+ новые монеты HTF": OT + extra("htf"),
         "+ новые SMC и HTF": OT + extra("smc") + extra("htf")}
    names = [k for k in D if k != "or"]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, [(nm, sd, w) for nm in names for sd in SEEDS for w in W], chunksize=2)
    R = {}
    for nm, sd, A, v in res: R.setdefault(nm, {}).setdefault(A, []).append(v)
    b = np.array([np.mean([x[0] for x in R[names[0]][A]]) for A, _ in W])
    for nm in names:
        E = np.array([np.mean([x[0] for x in R[nm][A]]) for A, _ in W]); dd = np.array([np.mean([x[1] for x in R[nm][A]]) for A, _ in W])
        print(f"{nm:22s} 6 мес. со $100: худшее ${E.min():,.0f} медиана ${np.median(E):,.0f} лучшее ${E.max():,.0f} просадка {np.median(dd)*100:.0f}% | лучше в {int((E > b * 1.001).sum())}/{len(W)}", flush=True)
    print("newcoins done", flush=True)
