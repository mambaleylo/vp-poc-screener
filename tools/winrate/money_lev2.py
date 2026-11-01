"""the leverage ceiling once more (the user: "почему тут 14 плечо? … можно же было открыть сделку на 5 долларов с 42 плечом —
тогда проблема с нехваткой маржи уйдет"): with cross margin the leverage changes only the margin a position locks (the risk
at the stop and the liquidation — by the whole balance — are the same), so a higher ceiling lets more positions be open at
once. The bundle ⚡ + P/R + SMC + EMA + HTF by the strictest money, 17 / 20 / 25 / 30 / 40 / 50x (each coin within its own
Binance brackets), 144 windows x 2 seeds; how often the free margin cut or skipped a trade"""
import sys, os, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X, money_rbx as RB
from multiprocessing import Pool
F = RB.F; SEEDS = (1, 2)
LEVS = [int(x) for x in os.environ.get("LEVS", "17,20,25,30,40,50").split(",")]   # 150 = no ceiling: each coin its own Binance maximum at the position's size
VARS = {(f"{c}x" if c < 150 else "максимум монеты"): F.replace("cap=17", f"cap={c}") for c in LEVS}
if os.environ.get("NOMG"): VARS["маржа без ограничений"] = F + "|nomg=1"
_D = {}
def _init(D): _D.update(D)
def job(a):
    v, sd, A = a
    return v, sd, A, MA2.run(_D["or"], _D["ot"], A, A + 365 * 86400, VARS[v], sd)
if __name__ == "__main__":
    D = {"or": MA2.orders(), "ot": [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]}
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, [(v, sd, A) for v in VARS for sd in SEEDS for A in X.STARTS], chunksize=8)
    R = {}
    for v, sd, A, x in res: R.setdefault(v, {}).setdefault(A, []).append(x)
    b = np.array([np.mean([x[0] for x in R["17x"][A]]) for A in X.STARTS])
    print("плечо | обычный год | плохой год | просадка медиана | в плохом окне | лучше 17x | по годам старта 2023 / 2024 / 2025 (медиана)", flush=True)
    for v in VARS:
        E = np.array([np.mean([x[0] for x in R[v][A]]) for A in X.STARTS]); dd = np.array([np.mean([x[1] for x in R[v][A]]) for A in X.STARTS])
        yrs = [np.median([E[i] for i, A in enumerate(X.STARTS) if M.ts(y) <= A < M.ts(y + 1)]) for y in (2023, 2024, 2025)]
        print(f"{v} | ${np.median(E):,.0f} | ${np.percentile(E, 10):,.0f} | {np.median(dd) * 100:.0f}% | {np.percentile(dd, 90) * 100:.0f}% | {int((E > b * 1.001).sum())}/{len(b)} | "
              + " / ".join(f"${y_:,.0f}" for y_ in yrs), flush=True)
    print("money lev2 done", flush=True)
