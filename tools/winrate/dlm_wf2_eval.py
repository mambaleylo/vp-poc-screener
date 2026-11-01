"""dlm_wf2.py's variants compared: the pool by the bot's rules (dlm_pool.py) of each variant's scores, walked with the
model file's exits; the trades' R by year on the bot's / check / new coins, and the bundle's money (a year from $100, 144
weekly windows, the ⚡ trades of an hour in a random order, 5 orders; the bot's settings). usage: dlm_wf2_eval.py NAME..."""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlm_exits as DX, dlm_pool as DP, money_multi as M, money_expect as X, money_osc as O, money_params as MP, money_order as MOR
from multiprocessing import Pool
NAMES = sys.argv[1:]; SEEDS = [1, 2, 3, 4, 5]
m = json.load(open("/home/user/vp-poc-screener/vp_dlm_model.json")); S0 = m["streams"][0]
EXK = dict(take=S0["take_atr"], soft=S0["stop_atr"], hard=S0["hard_stop_atr"])
def lv_pool(groups, sdir):
    P = DP.pool(groups, sdir=sdir); key = {}
    for st in ("wick4h", "close2h"):
        z = np.load(f"{sdir}/scores_{st}.npz", allow_pickle=True)
        for c, t, s, lv in zip(z["coin"], z["t"], z["side"], z["lv"]): key[(st, str(c), int(t), int(s))] = float(lv)
    for x in P: x["lv"] = key[(x["st"], x["coin"], x["t0"], x["side"])]
    return P
_E = {}
def _init(E): _E.update(E)
def job(a):
    nm, sd, A = a
    return nm, sd, A, M.run(_E[(nm, sd)], A, A + 365 * 86400, 14.0, O.W_OSC, eq0=100.0, heat=0.95, rk_=MP.rk(emx=3.0))
yr = lambda W: np.array([int(np.datetime64(x["t1h"], "s").astype("datetime64[Y]").astype(int) + 1970) for x in W])
if __name__ == "__main__":
    E = {}
    for nm in NAMES:
        sdir = f"{M.ST}/wf" if nm == "deployed_recipe" else f"{M.ST}/wf/var_{nm}"
        line = []
        for g, groups in (("бот", ["train", "check", "base"]), ("check", ["check"]), ("new", ["new"])):
            W = DX.walk(lv_pool(groups, sdir), **EXK); r = np.array([x["R"] for x in W]); y = yr(W)
            line.append(f"{g} {len(r)} сд. {r.mean():+.3f} (" + " ".join(f"{r[y == v].mean():+.2f}" for v in (2023, 2024, 2025, 2026)) + ")")
            if g == "бот":
                for sd in SEEDS: E[(nm, sd)] = MOR.events(W, sd)
        print(f"{nm:16s} " + " | ".join(line), flush=True)
    with Pool(4, initializer=_init, initargs=(E,)) as Pl:
        res = Pl.map(job, [(nm, sd, A) for nm in NAMES for sd in SEEDS for A in X.STARTS], chunksize=12)
    R = {}
    for nm, sd, A, r in res: R.setdefault((nm, sd), {})[A] = r
    for nm in NAMES:
        Ea = [np.array([R[(nm, sd)][A][0] for A in X.STARTS]) for sd in SEEDS]
        dd = np.mean([np.median([R[(nm, sd)][A][3] for A in X.STARTS]) for sd in SEEDS]) * 100
        print(f"{nm:16s} плохой ${np.mean([np.percentile(e, 10) for e in Ea]):>7,.0f} обычный ${np.mean([np.median(e) for e in Ea]):>7,.0f} просадка {dd:.0f}%", flush=True)
