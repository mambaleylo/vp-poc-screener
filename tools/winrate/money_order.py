"""how much the order inside an hour matters: the ⚡ trades touched in the same hour ordered by the model's score (the lab's
pool) vs at random (the bot: whichever level the price reaches first gets the room) — 5 random orders; the bundle's money
(money_expect.py's) for the bot's exits and the candidates of dlm_exits.py. -> the table"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlm_exits as DX, money_multi as M, money_expect as X, money_osc as O, money_params as MP
from multiprocessing import Pool
VAR = {"сейчас": {}, "тейк 1.3": {"take": 1.3}, "время 48": {"hold": 48}, "время 64": {"hold": 64}, "стоп 1.5": {"soft": 1.5}}
if len(sys.argv) > 1 and sys.argv[1] == "2":
    VAR = {"сейчас": {}, "стоп 1.5 + тейк 1.3": {"soft": 1.5, "take": 1.3}, "стоп 1.5 + тейк 1.1": {"soft": 1.5}, "стоп 1.5 + тейк 1.3 + авар 2.5": {"soft": 1.5, "take": 1.3, "hard": 2.5},
           "стоп 1.5 + тейк 1.2": {"soft": 1.5, "take": 1.2}, "стоп 1.75 + тейк 1.2": {"soft": 1.75, "take": 1.2}, "стоп 1.5 + тейк 1.3 + время 64": {"soft": 1.5, "take": 1.3, "hold": 64}}
SEEDS = [None, 1, 2, 3, 4, 5]
def events(Pw, seed):
    rng = np.random.default_rng(seed) if seed is not None else None
    key = (lambda x: (x["t1h"], -x["score"])) if seed is None else (lambda x: (x["t1h"], rng.random()))
    xs = sorted(Pw, key=lambda x: (x["t1h"], -x["score"])) if seed is None else sorted(Pw, key=lambda x: x["t1h"])
    if seed is not None:
        r = {id(x): rng.random() for x in xs}; xs = sorted(xs, key=lambda x: (x["t1h"], r[id(x)]))
    EV = [{"t0": x["t1h"] + 3600, "t1": x["tout"], "r": x["R"], "st": abs(x["fill"] - x["sl"]) / x["fill"], "sth": abs(x["fill"] - x["hsl"]) / x["fill"],
           "mod": "dlm", "sym": M.bn(x["coin"]), "side": x["side"], "e": x["fill"], "stream": x["st"]} for x in xs]
    EV += [v for v in M.build("base") if v["mod"] != "dlm"]
    EV.sort(key=lambda v: v["t0"]); return EV
_E = {}
def _init(E): _E.update(E)
def job(a):
    k, A = a
    return k, A, M.run(_E[k], A, A + 365 * 86400, 14.0, O.W_OSC, eq0=100.0, heat=0.95, rk_=MP.rk(emx=3.0))
if __name__ == "__main__":
    P = DX.pool_lv(); E = {}
    for nm, kw in VAR.items():
        Pw = DX.walk(P, **kw)
        for sd in SEEDS: E[(nm, sd)] = events(Pw, sd)
    with Pool(4, initializer=_init, initargs=(E,)) as Pl:
        res = Pl.map(job, [(k, A) for k in E for A in X.STARTS + [X.LAST]], chunksize=8)
    R = {}
    for k, A, r in res: R.setdefault(k, {})[A] = r
    for nm in VAR:
        row = []
        for sd in SEEDS:
            Ea = np.array([R[(nm, sd)][A][0] for A in X.STARTS]); dd = np.array([R[(nm, sd)][A][3] for A in X.STARTS])
            b0 = np.array([R[("сейчас", sd)][A][0] for A in X.STARTS])
            row.append((np.percentile(Ea, 10), np.median(Ea), np.median(dd) * 100, (Ea > b0 * 1.001).sum()))
        sc = row[0]; rn = np.array(row[1:])
        print(f"{nm:32s} по оценке: плохой ${sc[0]:,.0f} обычный ${sc[1]:,.0f} просадка {sc[2]:.0f}% | случайно (5): плохой ${rn[:,0].mean():,.0f} обычный ${rn[:,1].mean():,.0f} "
              f"(${rn[:,1].min():,.0f}..${rn[:,1].max():,.0f}) просадка {rn[:,2].mean():.0f}% | лучше 'сейчас' в {rn[:,3].mean():.0f}/144", flush=True)
