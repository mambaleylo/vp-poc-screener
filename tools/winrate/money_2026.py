"""⚡ the bot as it is (the deployed trees, trained to 2025-12-29) vs the lab's models on 2026 ONLY (out of sample for both):
per stream the fills and R of 2026, then the strictest money 2026-01-01 .. 2026-10-01 (the bundle, 8 seeds) for the combos"""
import sys, os, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
F = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125"; A, B = 1767225600, 1790812800
VARS = {"бот как есть": "dd", "4ч бот + 2ч лаб": "dl", "4ч лаб + 2ч бот": "ld", "4ч лаб + 2ч лаб": "ll"}
_D = {}
def _init(D): _D.update(D)
def job(a):
    v, sd = a
    return v, sd, MA2.run(_D[v], _D["ot"], A, B, F, sd)
if __name__ == "__main__":
    import money_4h   # makes the combo links
    D = {"ot": [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]}
    for v, c in VARS.items():
        D[v] = MA2.orders(f"_c{c}")
        print(v + ": " + " | ".join(f"{st} 2026 исполнено {len(f)}, R {np.mean([o['r'] for o in f]):+.3f}" for st in ("wick4h", "close2h")
                                     for f in [[o for o in D[v] if o["stream"] == st and o["filled"] and A <= o["t"] < B]]), flush=True)
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, [(v, sd) for v in VARS for sd in range(1, 9)])
    R = {}
    for v, sd, x in res: R.setdefault(v, []).append(x)
    print("вариант | $ к 1 октября 2026 со $100 на 1 января (среднее 8 прогонов) | просадка", flush=True)
    for v in VARS:
        print(f"{v} | ${np.mean([x[0] for x in R[v]]):,.0f} | {np.mean([x[1] for x in R[v]]) * 100:.0f}%", flush=True)
    print("money 2026 done", flush=True)
