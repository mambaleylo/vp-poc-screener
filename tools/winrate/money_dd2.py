"""lowering the drawdown, round 2 (money_dd.py: capping the bunches cut the money — the bunches are the best trades): keep the
trades, soften the market's blow — a BTC hedge while N+ ⚡ are open on one side (money_arm2 "hedge=N/F"); the risk x0.5 against
BTC's weekly trend (money_wk's state); both. The noise as money_dd (K paired runs, every 2nd window + the last 12 months).
usage: ALLSUF=_clr money_dd2.py [K]"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X, money_wk as WK
from multiprocessing import Pool
BASE = "Bn|arm=0.6|oth=1|dis=1.0|cap=125|slip=1|liq=4:0.5/8:0.25/12:0|heat=1.0"; K = int(ARGV[0]) if ARGV else 4; STARTS = X.STARTS[::2]
VARS = {"как в боте": ("", False), "хедж BTC: 1+ в сторону, 100% объёма": ("|hedge=1/1.0", False), "хедж BTC: 3+ в сторону, 100%": ("|hedge=3/1.0", False),
        "хедж BTC: 3+ в сторону, 50%": ("|hedge=3/0.5", False), "хедж BTC: 5+ в сторону, 100%": ("|hedge=5/1.0", False),
        "хедж BTC: 8+ в сторону, 100%": ("|hedge=8/1.0", False), "риск ×0.5 против недельного тренда BTC": ("", True),
        "хедж 3+/100% и ×0.5 против тренда BTC": ("|hedge=3/1.0", True)}
_D = {}
def _init(D): _D.update(D)
def job(a):
    v, k, A = a; suf, wk = VARS[v]
    return v, k, A, MA2.run(_D[(k, "or", wk)], _D[(k, "ot", wk)], A, A + 365 * 86400, BASE + suf, 1)
if __name__ == "__main__":
    base = MA2.orders(); o2 = [dict(o, xm=0.75) for o in MA2.stream_orders("wick4h_o2", "") if o["prio"] >= 1.05]
    OT = [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]; D = {}
    half = lambda v, t: (lambda x: dict(v, xm=v.get("xm", 1.0) * 0.5) if x["w_b"] < 0 else v)(WK.tag(v, t))
    for k in range(K):
        rng = np.random.default_rng(300 + k)
        Or = sorted([o for o in base + o2 if rng.random() >= 0.05], key=lambda o: o["t"]); Ot = [v for v in OT if rng.random() >= 0.05]
        D[(k, "or", False)] = Or; D[(k, "ot", False)] = Ot
        D[(k, "or", True)] = [half(o, o["t"]) for o in Or]; D[(k, "ot", True)] = [half(v, v["t0"]) for v in Ot]
    V = list(VARS)
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, [(v, k, A) for v in V for k in range(K) for A in STARTS + [X.LAST]], chunksize=4)
    R = {(v, k, A): r for v, k, A, r in res}; S = {}
    for v in V:
        S[v] = {q: [] for q in ("p50", "p10", "dd", "dd90", "last12")}
        for k in range(K):
            e = np.array([R[(v, k, A)][0] for A in STARTS]); dd = np.array([R[(v, k, A)][1] for A in STARTS])
            S[v]["p50"].append(float(np.median(e))); S[v]["p10"].append(float(np.percentile(e, 10))); S[v]["dd"].append(float(np.median(dd)))
            S[v]["dd90"].append(float(np.percentile(dd, 90))); S[v]["last12"].append(float(R[(v, k, X.LAST)][0]))
    b = S[V[0]]
    print(f"\nвариант | обычный год | плохой год | просадка обычная | в плохом окне | последние 12 мес — медиана {K} прогонов [лучше бота]", flush=True)
    for v in V:
        cell = []
        for q in ("p50", "p10", "dd", "dd90", "last12"):
            a = np.array(S[v][q]); bb = np.array(b[q]); better = int((a < bb).sum() if q.startswith("dd") else (a > bb).sum())
            cell.append((f"{np.median(a) * 100:.0f}%" if q.startswith("dd") else f"${np.median(a):,.0f}") + f" [{better}]")
        print(f"{v} | " + " | ".join(cell), flush=True)
    json.dump(S, open(f"{M.ST}/wf/money_dd2.json", "w"), indent=1)
    print("money dd2 done", flush=True)
