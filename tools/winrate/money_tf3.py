"""the money's noise (the user: "самое главное, чтобы потом не было так, что… шапку надо опять резать"): the shifted 4h stream
(wick4h_o2) and the 4h stream have the same trades' stats (R +0.287 / +0.288, WR 80 / 81%), yet "o2 + 2h" made $11.5k vs
"4h + 2h" $27.2k — the compounding money is very path-dependent. So: K perturbed runs — each drops a random 5% of every
module's trades / ⚡ orders (the same drop of the shared part for both variants: a paired test) — the bot as it is vs + o2,
every 2nd one-year window + the last 12 months + 2026; the spread and the paired wins. usage: ALLSUF=_clr money_tf3.py [K]"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
RULE = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125"; K = int(ARGV[0]) if ARGV else 8; DROP = 0.05
A26, B26 = M.ts(2026, 1, 1), M.ts(2026, 10, 1); STARTS = X.STARTS[::2]
_D = {}
def _init(D): _D.update(D)
def job(a):
    v, k, A, B = a
    return v, k, A, B, MA2.run(_D[(v, k, "or")], _D[(k, "ot")], A, B, RULE, 1)
if __name__ == "__main__":
    base = MA2.orders(); o2 = MA2.stream_orders("wick4h_o2", ""); OT = [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]
    D = {}
    for k in range(K):
        rng = np.random.default_rng(100 + k)
        kb = [o for o in base if rng.random() >= DROP]; ko = [o for o in o2 if rng.random() >= DROP]; D[(k, "ot")] = [v for v in OT if rng.random() >= DROP]
        D[("как в боте", k, "or")] = kb; D[("+ 4ч сдвиг", k, "or")] = sorted(kb + ko, key=lambda o: o["t"])
    V = ("как в боте", "+ 4ч сдвиг")
    jobs = [(v, k, A, A + 365 * 86400) for v in V for k in range(K) for A in STARTS + [X.LAST]] + [(v, k, A26, B26) for v in V for k in range(K)]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, jobs, chunksize=4)
    R = {(v, k, A, B): r[0] for v, k, A, B, r in res}
    S = {v: {"p50": [], "p10": [], "last12": [], "y26": []} for v in V}
    print("прогон | как в боте: обычный / плохой / посл. 12 / 2026 | + 4ч сдвиг: обычный / плохой / посл. 12 / 2026", flush=True)
    for k in range(K):
        row = []
        for v in V:
            e = np.array([R[(v, k, A, A + 365 * 86400)] for A in STARTS])
            x = {"p50": np.median(e), "p10": np.percentile(e, 10), "last12": R[(v, k, X.LAST, X.LAST + 365 * 86400)], "y26": R[(v, k, A26, B26)]}
            for q in x: S[v][q].append(float(x[q]))
            row.append(" / ".join(f"${x[q]:,.0f}" for q in ("p50", "p10", "last12", "y26")))
        print(f"{k + 1} | " + " | ".join(row), flush=True)
    print("\nитог: медиана прогонов (мин … макс) | сдвиг лучше в прогонах", flush=True)
    for q, nm in (("p50", "обычный год"), ("p10", "плохой год"), ("last12", "последние 12 мес"), ("y26", "2026")):
        a, b = np.array(S[V[0]][q]), np.array(S[V[1]][q])
        print(f"{nm}: как в боте ${np.median(a):,.0f} (${a.min():,.0f} … ${a.max():,.0f}) | + сдвиг ${np.median(b):,.0f} (${b.min():,.0f} … ${b.max():,.0f}) | {int((b > a).sum())}/{K}", flush=True)
    json.dump(S, open(f"{M.ST}/wf/money_tf3.json", "w"), indent=1)
    print("money tf3 done", flush=True)
