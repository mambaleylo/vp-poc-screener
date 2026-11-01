"""the drawdown (the user: "посадку можно уменьшить? поработай с фильтрами") of the bundle with the model-picked 4h
breakout (money_rbs.py's A: stop 1.5 ATR, take 2R, <= 2 days, the score > 0.8): the breakout's own filters (its risk,
at most N open, N a side, with BTC's EMA200, longs / shorts only) and the bundle's levers (every risk x0.75, the
open-risk cap 80%, 14x, the risk down after a drawdown) -> the usual / bad year, the median and the bad-window drawdown"""
import sys, os, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X, money_params as MP, money_rbx as RB, money_rbs as MR, rbs_feat as RF
from multiprocessing import Pool
SEEDS = (1, 2)


def cap_open(tr, n=None, side_n=None):
    """the breakout's trades with at most n open (side_n a side) — the earlier first"""
    out, opn = [], []
    for v in sorted(tr, key=lambda v: v["t0"]):
        opn = [o for o in opn if o["t1"] > v["t0"]]
        if n and len(opn) >= n: continue
        if side_n and sum(1 for o in opn if o["side"] == v["side"]) >= side_n: continue
        out.append(v); opn.append(v)
    return out


F = RB.F
VARS = {   # name: (the list's filter, the breakout's risk %, the rule string, the other risks x)
    "без пробоя": (None, 0.0, F, 1.0),
    "A 1% (как было)": ("all", 1.0, F, 1.0),
    "A 0.75%": ("all", 0.75, F, 1.0),
    "A 0.5%": ("all", 0.5, F, 1.0),
    "A 1%, не больше 3 открытых": ("n3", 1.0, F, 1.0),
    "A 1%, не больше 2 открытых": ("n2", 1.0, F, 1.0),
    "A 1%, не больше 2 в сторону": ("s2", 1.0, F, 1.0),
    "A 1%, по тренду BTC": ("btc", 1.0, F, 1.0),
    "A 1%, только лонги": ("long", 1.0, F, 1.0),
    "A 1%, только шорты": ("short", 1.0, F, 1.0),
    "A 1% + все риски x0.75": ("all", 0.75, F, 0.75),
    "A 1% + общий лимит риска 80%": ("all", 1.0, F.replace("heat=1.0", "heat=0.8"), 1.0),
    "A 1% + плечо 14x": ("all", 1.0, F.replace("cap=17", "cap=14"), 1.0),
    "A 1% + риск x0.5 после просадки 35%": ("all", 1.0, F + "|ddc=0.35/0.5/0.15", 1.0),
    "без пробоя + все риски x0.75": (None, 0.0, F, 0.75),
}
_D = {}
def _init(D): _D.update(D)
def job(a):
    v, sd, A = a
    flt, rk, rule, kx = VARS[v]
    OT = _D["ot"] + (_D[flt] if flt else [])
    r0 = {m_: x_ * kx for m_, x_ in MP.rk(emx=3.0).items()}
    return v, sd, A, MA2.run(_D["or"], OT, A, A + 365 * 86400, rule, sd, rk=dict(r0, rbs=rk))


if __name__ == "__main__":
    import numpy as np
    tr = MR.trades(1.5, "t2", 2, 0.8)
    # BTC's EMA200 side at the signal (rbs_feat's b_e200, signed by the trade's side) -> the trades with it
    z = dict(np.load(f"{MR.ML.ST}/wf/rbs_4.npz")); Xf = np.load(f"{MR.ML.ST}/wf/rbs_4_X.npz")["X"]; ib = RF.NAMES.index("b_e200")
    key = {(str(s), int(t), int(d)): Xf[k, ib] for k, (s, t, d) in enumerate(zip(z["sym"], z["t"], z["side"]))}
    D = {"or": MA2.orders(), "ot": [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}],
         "all": tr, "n3": cap_open(tr, 3), "n2": cap_open(tr, 2), "s2": cap_open(tr, side_n=2),
         "btc": [v for v in tr if key.get((v["sym"], v["t0"], v["side"]), 0) > 0],
         "long": [v for v in tr if v["side"] > 0], "short": [v for v in tr if v["side"] < 0]}
    for k in ("all", "n3", "n2", "s2", "btc", "long", "short"):
        rs = np.array([v["r"] for v in D[k]]); print(f"{k}: {len(rs)} сделок {rs.mean():+.3f}R", flush=True)
    jobs = [(v, sd, A) for v in VARS for sd in SEEDS for A in X.STARTS]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, jobs, chunksize=8)
    R = {}
    for v, sd, A, x in res: R.setdefault(v, {}).setdefault(A, []).append(x)
    b = np.array([np.mean([x[0] for x in R["без пробоя"][A]]) for A in X.STARTS])
    print("вариант | обычный год | плохой год | просадка медиана | просадка в плохом окне (1 из 10) | лучше нынешнего", flush=True)
    for v in VARS:
        E = np.array([np.mean([x[0] for x in R[v][A]]) for A in X.STARTS]); dd = np.array([np.mean([x[1] for x in R[v][A]]) for A in X.STARTS])
        print(f"{v} | ${np.median(E):,.0f} | ${np.percentile(E, 10):,.0f} | {np.median(dd) * 100:.0f}% | {np.percentile(dd, 90) * 100:.0f}% | {int((E > b * 1.001).sum())}/{len(b)}", flush=True)
    print("money rbs2 done", flush=True)
