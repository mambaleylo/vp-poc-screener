"""⚡ the close stop x the take grid on the walk-forward pool: the trades' R on the bot's coins / the check coins / the new
coins (by year) and the bundle's money with the ⚡ trades of an hour in a random order (5 orders — the bot: the first
level the price reaches gets the room). -> <LABSTORE>/wf/dlm_exits_grid.json"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlm_exits as DX, dlm_pool as DP, money_multi as M, money_expect as X, money_osc as O, money_params as MP, money_order as MO
from multiprocessing import Pool
SOFT = [1.5, 1.75, 2.0, 2.25]; TAKE = [1.0, 1.1, 1.2, 1.3, 1.5]; SEEDS = [1, 2, 3, 4, 5]
def lv_pool(groups):
    P = DP.pool(groups); key = {}
    for st in ("wick4h", "close2h"):
        z = np.load(f"{DP.ST}/wf/scores_{st}.npz", allow_pickle=True)
        for c, t, s, lv in zip(z["coin"], z["t"], z["side"], z["lv"]): key[(st, str(c), int(t), int(s))] = float(lv)
    for x in P: x["lv"] = key[(x["st"], x["coin"], x["t0"], x["side"])]
    return P
_E = {}
def _init(E): _E.update(E)
def job(a):
    k, A = a
    return k, A, M.run(_E[k], A, A + 365 * 86400, 14.0, O.W_OSC, eq0=100.0, heat=0.95, rk_=MP.rk(emx=3.0))
if __name__ == "__main__":
    PB = lv_pool(["train", "check", "base"]); PC = lv_pool(["check"]); PN = lv_pool(["new"])
    E = {}; S = {}
    yr = lambda Pw: np.array([int(np.datetime64(x["t1h"], "s").astype("datetime64[Y]").astype(int) + 1970) for x in Pw])
    for so in SOFT:
        for tk in TAKE:
            k = (so, tk); kw = {"soft": so, "take": tk}
            Pw = DX.walk(PB, **kw)
            for sd in SEEDS: E[(k, sd)] = MO.events(Pw, sd)
            row = {}
            for nm, P_ in (("бот", None), ("check", PC), ("new", PN)):
                W = Pw if P_ is None else DX.walk(P_, **kw); r = np.array([x["R"] for x in W]); y = yr(W)
                row[nm] = {"R": float(r.mean()), "years": [float(r[y == yy].mean()) for yy in (2023, 2024, 2025, 2026)]}
            S[f"{so}/{tk}"] = row
    with Pool(4, initializer=_init, initargs=(E,)) as Pl:
        res = Pl.map(job, [(k, A) for k in E for A in X.STARTS], chunksize=12)
    R = {}
    for k, A, r in res: R.setdefault(k, {})[A] = r
    base = {sd: np.array([R[((2.0, 1.1), sd)][A][0] for A in X.STARTS]) for sd in SEEDS}
    print("стоп/тейк | R бот / check / new (годы new) | деньги (случайный порядок, 5): плохой · обычный · просадка · лучше нынешнего", flush=True)
    for so in SOFT:
        for tk in TAKE:
            k = (so, tk); row = S[f"{so}/{tk}"]
            p10 = np.mean([np.percentile([R[(k, sd)][A][0] for A in X.STARTS], 10) for sd in SEEDS])
            p50 = np.mean([np.median([R[(k, sd)][A][0] for A in X.STARTS]) for sd in SEEDS])
            dd = np.mean([np.median([R[(k, sd)][A][3] for A in X.STARTS]) for sd in SEEDS]) * 100
            bt = np.mean([(np.array([R[(k, sd)][A][0] for A in X.STARTS]) > base[sd] * 1.001).sum() for sd in SEEDS])
            row.update(p10=p10, p50=p50, dd=dd, better=bt)
            print(f"{so:4} / {tk:3} | {row['бот']['R']:+.3f} / {row['check']['R']:+.3f} / {row['new']['R']:+.3f} ({' '.join(f'{v:+.2f}' for v in row['new']['years'])}) | "
                  f"${p10:>6,.0f} · ${p50:>7,.0f} · {dd:.0f}% · {bt:.0f}/144", flush=True)
    json.dump(S, open(f"{M.ST}/wf/dlm_exits_grid.json", "w"), indent=1)
