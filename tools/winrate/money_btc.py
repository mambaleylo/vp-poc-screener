"""a BTC rule over ⚡'s risk (dlm_btc.py: the shorts while BTC rose over 7 days the weakest, the longs while it fell the
best, on the bot's / check / new coins): the bundle's money with the random order (5), the bot's exits and the candidate.
-> the table"""
import sys, os, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlm_exits as DX, dlm_btc as BT, money_multi as M, money_expect as X, money_osc as O, money_params as MP, money_order as MOR
from multiprocessing import Pool
SEEDS = [1, 2, 3, 4, 5]
def r7(v):
    j = np.searchsorted(BT.u, (v["t0"] - 3600) // 86400) - 1
    return BT.DC[j] / BT.DC[j - 7] - 1 if j >= 60 else 0.0
RULE = {"сейчас": lambda v: 1.0,
        "шорты при росте BTC x0.5": lambda v: 0.5 if v["mod"] == "dlm" and v["side"] < 0 and r7(v) > 0 else 1.0,
        "лонги при падении BTC x1.25": lambda v: 1.25 if v["mod"] == "dlm" and v["side"] > 0 and r7(v) < 0 else 1.0,
        "оба": lambda v: (0.5 if v["side"] < 0 and r7(v) > 0 else (1.25 if v["side"] > 0 and r7(v) < 0 else 1.0)) if v["mod"] == "dlm" else 1.0}
_E = {}
def _init(E): _E.update(E)
def job(a):
    ex, nm, sd, A = a
    return ex, nm, sd, A, M.run(_E[(ex, sd)], A, A + 365 * 86400, 14.0, lambda v: O.W_OSC(v) * RULE[nm](v), eq0=100.0, heat=0.95, rk_=MP.rk(emx=3.0))
if __name__ == "__main__":
    P = DX.pool_lv(); E = {}; EX = {"2.0/1.1": {}, "1.75/1.2": {"soft": 1.75, "take": 1.2}}
    for ex, kw in EX.items():
        Pw = DX.walk(P, **kw)
        for sd in SEEDS: E[(ex, sd)] = MOR.events(Pw, sd)
    with Pool(4, initializer=_init, initargs=(E,)) as Pl:
        res = Pl.map(job, [(ex, nm, sd, A) for ex in EX for nm in RULE for sd in SEEDS for A in X.STARTS], chunksize=12)
    R = {}
    for ex, nm, sd, A, r in res: R.setdefault((ex, nm, sd), {})[A] = r
    for ex in EX:
        print("выходы", ex)
        for nm in RULE:
            E_ = {sd: np.array([R[(ex, nm, sd)][A][0] for A in X.STARTS]) for sd in SEEDS}
            b = {sd: np.array([R[(ex, "сейчас", sd)][A][0] for A in X.STARTS]) for sd in SEEDS}
            print(f"   {nm:28s} плохой ${np.mean([np.percentile(E_[s], 10) for s in SEEDS]):>7,.0f} обычный ${np.mean([np.median(E_[s]) for s in SEEDS]):>7,.0f} "
                  f"просадка {np.mean([np.median([R[(ex, nm, s)][A][3] for A in X.STARTS]) for s in SEEDS])*100:.0f}% | лучше в {np.mean([(E_[s] > b[s]*1.001).sum() for s in SEEDS]):.0f}/144", flush=True)
