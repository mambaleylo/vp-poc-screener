"""the BTC hedge 10+/100% (money_dd2 round 3's best) by the windows' start year: does it help only the windows of 2023 (its
squeezes) and cost the later ones? K paired runs, every window; the median year and drawdown by the start year (2023 / 2024 /
2025) + the last 12 months. usage: ALLSUF=_clr money_hedge_y.py [K]"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
BASE = "Bn|arm=0.6|oth=1|dis=1.0|cap=125|slip=1|liq=4:0.5/8:0.25/12:0|heat=1.0"; K = int(ARGV[0]) if ARGV else 2
VARS = {"как в боте": "", "хедж 10+/100%": "|hedge=10/1.0", "хедж 8+/50%": "|hedge=8/0.5"}
_D = {}
def _init(D): _D.update(D)
def job(a):
    v, k, A = a
    return v, k, A, MA2.run(_D[(k, "or")], _D[(k, "ot")], A, A + 365 * 86400, BASE + VARS[v], 1)
if __name__ == "__main__":
    base = MA2.orders(); o2 = [dict(o, xm=0.75) for o in MA2.stream_orders("wick4h_o2", "") if o["prio"] >= 1.05]
    OT = [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]; D = {}
    for k in range(K):
        rng = np.random.default_rng(300 + k)
        D[(k, "or")] = sorted([o for o in base + o2 if rng.random() >= 0.05], key=lambda o: o["t"]); D[(k, "ot")] = [v for v in OT if rng.random() >= 0.05]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, [(v, k, A) for v in VARS for k in range(K) for A in X.STARTS + [X.LAST]], chunksize=4)
    R = {(v, k, A): r for v, k, A, r in res}; yrs = np.array([int(str(np.datetime64(A, "s"))[:4]) for A in X.STARTS])
    print("вариант | старт 2023: год, просадка | старт 2024 | старт 2025 | последние 12 мес", flush=True)
    for v in VARS:
        cells = []
        for Y in (2023, 2024, 2025):
            e = [np.median([R[(v, k, A)][0] for A, y in zip(X.STARTS, yrs) if y == Y]) for k in range(K)]
            d = [np.median([R[(v, k, A)][1] for A, y in zip(X.STARTS, yrs) if y == Y]) for k in range(K)]
            cells.append(f"${np.median(e):,.0f}, {np.median(d) * 100:.0f}%")
        cells.append(f"${np.median([R[(v, k, X.LAST)][0] for k in range(K)]):,.0f}, {np.median([R[(v, k, X.LAST)][1] for k in range(K)]) * 100:.0f}%")
        print(f"{v} | " + " | ".join(cells), flush=True)
    print("hedge y done", flush=True)
