"""the selection bias check: every decision of v0.99.746..754 against its alternative on the strictest money
(money_arm2.py), the 12-month windows split — the early ones (starting before 2024-07, the years the choices could have been
made on) and the late ones (starting from 2025-01, unseen if one had chosen early): does the early winner win late too?
usage: money_split.py -> the table + <LABSTORE>/wf/money_split.json"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
F = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0"
ALT = {"бот до v0.99.753": "A", "выставление 0.3 ATR": F.replace("arm=0.6", "arm=0.3"), "выставление 1.0 ATR": F.replace("arm=0.6", "arm=1.0"),
       "снятие 1.6 ATR": F.replace("dis=1.0", "dis=1.6"), "лимит риска 95%": F.replace("heat=1.0", "heat=0.95"), "без «остальные первыми»": F.replace("|oth=1", ""),
       "без приоритета": F.replace("Bn|", "A|"), "старые выходы ⚡": F + "|ex=old", "плечо 10x": F + "|cap=10", "плечо 20x": F + "|cap=20",
       "без урезания 2ч-шортов": F + "|wf=nocut", "старый WaveTrend": F + "|wf=oldwt", "EMA 2%": F + "|emx=2"}
STARTS = X.STARTS[::2]; EARLY = [A for A in STARTS if A < M.ts(2024, 7)]; LATE = [A for A in STARTS if A >= M.ts(2025, 1)]
_D = {}
def _init(D): _D.update(D)
def job(a):
    rule, A = a
    if "ex=" in rule and not MA2.EXITS: MA2.EXITS["old"] = MA2.orders_exits(_D["or"], 1.1, 2.0)
    return rule, A, MA2.run(_D["or"], _D["ot"], A, A + 365 * 86400, rule, 1)[0]
if __name__ == "__main__":
    D = {"or": MA2.orders(), "ot": [v for v in M.build("base") if v["mod"] != "dlm"]}
    rules = [F] + list(ALT.values())
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, [(r, A) for r in rules for A in STARTS], chunksize=4)
    R = {}
    for r, A, v in res: R.setdefault(r, {})[A] = v
    out = {}
    print(f"окон: ранних {len(EARLY)}, поздних {len(LATE)}; итоговая схема: ранние медиана ${np.median([R[F][A] for A in EARLY]):,.0f}, поздние ${np.median([R[F][A] for A in LATE]):,.0f}")
    for nm, r in ALT.items():
        q = lambda W: np.array([R[F][A] / max(R[r][A], 1e-9) for A in W])
        e, l = q(EARLY), q(LATE)
        out[nm] = {"early_x": float(np.median(e)), "early_win": int((e > 1).sum()), "late_x": float(np.median(l)), "late_win": int((l > 1).sum())}
        o = out[nm]
        print(f"   итоговая против «{nm}»: ранние — лучше в {o['early_win']}/{len(EARLY)}, x{o['early_x']:.2f} | поздние — лучше в {o['late_win']}/{len(LATE)}, x{o['late_x']:.2f}", flush=True)
    json.dump(out, open(f"{M.ST}/wf/money_split.json", "w"), indent=1)
