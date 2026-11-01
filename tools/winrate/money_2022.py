"""the 2022 stress test (the bear market): ⚡ (dlm_allorders2022.py's orders) + the EMA / SMC trades the lists have in 2022,
the strictest money (money_arm2.run), the bot before v0.99.753 vs now; 6-month windows from $100 started every month
Jan..Jul 2022 and the whole year. -> the table"""
import sys, os, numpy as np
os.environ["ALLSUF"] = "_y2022"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import money_arm2 as MA2, money_multi as M
from multiprocessing import Pool
RULES = {"бот до v0.99.753": "A", "сейчас (v0.99.754)": "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0", "сейчас, плечо 20x": "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=20",
         "сейчас, риск ⚡ 3%": "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|dlm=3"}
if len(sys.argv) > 1 and sys.argv[1] == "deep":
    F = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0"
    RULES = {"сейчас (0.6 ATR, 14x)": F, "0.3 ATR": F.replace("arm=0.6", "arm=0.3"), "0.45 ATR": F.replace("arm=0.6", "arm=0.45"),
             "20x": F + "|cap=20", "0.3 ATR + 20x": F.replace("arm=0.6", "arm=0.3") + "|cap=20"}
W = [(M.ts(2022, m), M.ts(2022, m) + 182 * 86400) for m in range(1, 8)] + [(M.ts(2022, 1), M.ts(2023, 1))]
SEEDS = [1, 2, 3]
_D = {}
def _init(D): _D.update(D)
def job(a):
    nm, sd, (A, B) = a
    return nm, sd, A, B, MA2.run(_D["or"], _D["ot"], A, B, RULES[nm], sd)
if __name__ == "__main__":
    OR = MA2.orders(); OT = [v for v in M.build("base") if v["mod"] != "dlm" and M.ts(2022) <= v["t0"] < M.ts(2023)]
    print("⚡ заявок 2022:", len(OR), "исполнились", sum(o["filled"] for o in OR), "· средний R исполнившихся", round(np.mean([o["r"] for o in OR if o["filled"]]), 3), "· EMA/SMC сделок", len(OT), flush=True)
    with Pool(4, initializer=_init, initargs=({"or": OR, "ot": OT},)) as Pl:
        res = Pl.map(job, [(nm, sd, w) for nm in RULES for sd in SEEDS for w in W], chunksize=2)
    R = {}
    for nm, sd, A, B, v in res: R.setdefault(nm, {}).setdefault((A, B), []).append(v)
    for nm in RULES:
        six = [np.mean([x[0] for x in R[nm][w]]) for w in W[:-1]]; yr = np.mean([x[0] for x in R[nm][W[-1]]]); dd = np.mean([x[1] for x in R[nm][W[-1]]]) * 100
        print(f"{nm:22s} 6 мес. со $100: худшее ${min(six):,.0f} медиана ${np.median(six):,.0f} лучшее ${max(six):,.0f} | весь 2022: ${yr:,.0f}, просадка {dd:.0f}%", flush=True)
    print("done", flush=True)
