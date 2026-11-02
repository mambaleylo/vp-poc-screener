"""the risk level vs the money and the drawdown (the user chose to pick the comfortable drawdown himself after money_dd*: no rule
lowers it without much money lost): the bot as it trades from v0.99.768 (money_hdr2's config) with every module's risk x k
(money_arm2 "k=": ⚡ 4.5% x k, P/R 3%, SMC 2.5%, EMA 3%, HTF 2% x k), K paired runs (the same 5% dropped), every 2nd window + the
last 12 months: the usual / bad year, the drawdown in the usual and the bad window. usage: ALLSUF=_clr money_risk.py [K]"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
BASE = "Bn|arm=0.6|oth=1|dis=1.0|cap=125|slip=1|liq=4:0.5/8:0.25/12:0|heat=1.0"; K = int(ARGV[0]) if ARGV else 4; STARTS = X.STARTS[::2]
KS = (1.0, 0.85, 0.75, 0.65, 0.55, 0.45)
_D = {}
def _init(D): _D.update(D)
def job(a):
    kk, k, A = a
    return kk, k, A, MA2.run(_D[(k, "or")], _D[(k, "ot")], A, A + 365 * 86400, BASE + ("" if kk == 1.0 else f"|k={kk}"), 1)
if __name__ == "__main__":
    base = MA2.orders(); o2 = [dict(o, xm=0.75) for o in MA2.stream_orders("wick4h_o2", "") if o["prio"] >= 1.05]
    OT = [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]; D = {}
    for k in range(K):
        rng = np.random.default_rng(300 + k)
        D[(k, "or")] = sorted([o for o in base + o2 if rng.random() >= 0.05], key=lambda o: o["t"]); D[(k, "ot")] = [v for v in OT if rng.random() >= 0.05]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, [(kk, k, A) for kk in KS for k in range(K) for A in STARTS + [X.LAST]], chunksize=4)
    R = {(kk, k, A): r for kk, k, A, r in res}; out = {}
    print(f"риск ×k (⚡ %) | обычный год | плохой год | просадка обычная | в плохом окне | последние 12 мес — медиана {K} прогонов", flush=True)
    for kk in KS:
        q = {n: [] for n in ("p50", "p10", "dd", "dd90", "last12")}
        for k in range(K):
            e = np.array([R[(kk, k, A)][0] for A in STARTS]); dd = np.array([R[(kk, k, A)][1] for A in STARTS])
            q["p50"].append(np.median(e)); q["p10"].append(np.percentile(e, 10)); q["dd"].append(np.median(dd)); q["dd90"].append(np.percentile(dd, 90))
            q["last12"].append(R[(kk, k, X.LAST)][0])
        out[str(kk)] = {n: float(np.median(v)) for n, v in q.items()}
        o = out[str(kk)]
        print(f"×{kk} ({4.5 * kk:.2f}%) | ${o['p50']:,.0f} | ${o['p10']:,.0f} | {o['dd'] * 100:.0f}% | {o['dd90'] * 100:.0f}% | ${o['last12']:,.0f}", flush=True)
    json.dump(out, open(f"{M.ST}/wf/money_risk.json", "w"), indent=1)
    print("money risk done", flush=True)
