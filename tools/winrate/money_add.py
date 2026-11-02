"""the shifted 4h stream adding to a held ⚡ position (the user: "а если для 4ч со сдвигом сделать исключение и добирать
позицию?"): the bundle + the approved o2 (score >= 1.05 x the threshold, risk x0.75) as is (one position a coin) vs o2's limit
allowed onto the same side's ⚡ position (money_arm2 "add": a separate leg with its own exits), vs only onto the standard 4h
stream's. The noise as money_tf3 (K paired runs dropping the same 5%, every 2nd window + the last 12 months + 2026); the
number of add-on legs a year. usage: ALLSUF=_clr money_add.py [K]"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
RULE = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125"; K = int(ARGV[0]) if ARGV else 6; DROP = 0.05
A26, B26 = M.ts(2026, 1, 1), M.ts(2026, 10, 1); STARTS = X.STARTS[::2]
VARS = {"сдвиг как утверждён (без добора)": "", "добор к любой позиции ⚡": "|add=wick4h_o2", "добор только к обычному 4ч": "|add=wick4h_o2|addon=wick4h"}
_D = {}
def _init(D): _D.update(D)
def job(a):
    v, k, A, B = a
    return v, k, A, B, MA2.run(_D[k], _D[(k, "ot")], A, B, RULE + VARS[v], 1)
if __name__ == "__main__":
    base = MA2.orders(); OT = [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]
    o2 = [dict(o, xm=0.75) for o in MA2.stream_orders("wick4h_o2", "") if o["prio"] >= 1.05]
    D = {}
    for k in range(K):
        rng = np.random.default_rng(100 + k)
        D[k] = sorted([o for o in base + o2 if rng.random() >= DROP], key=lambda o: o["t"]); D[(k, "ot")] = [v for v in OT if rng.random() >= DROP]
    V = list(VARS)
    jobs = [(v, k, A, A + 365 * 86400) for v in V for k in range(K) for A in STARTS + [X.LAST]] + [(v, k, A26, B26) for v in V for k in range(K)]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, jobs, chunksize=4)
    R = {(v, k, A, B): r for v, k, A, B, r in res}
    S = {v: {q: [] for q in ("p50", "p10", "dd", "last12", "y26", "fills")} for v in V}
    for v in V:
        for k in range(K):
            e = np.array([R[(v, k, A, A + 365 * 86400)][0] for A in STARTS]); dd = np.array([R[(v, k, A, A + 365 * 86400)][1] for A in STARTS])
            S[v]["p50"].append(float(np.median(e))); S[v]["p10"].append(float(np.percentile(e, 10))); S[v]["dd"].append(float(np.median(dd)))
            S[v]["last12"].append(float(R[(v, k, X.LAST, X.LAST + 365 * 86400)][0])); S[v]["y26"].append(float(R[(v, k, A26, B26)][0]))
            S[v]["fills"].append(float(np.mean([R[(v, k, A, A + 365 * 86400)][2] for A in STARTS])))
    c = V[0]
    print(f"\nвариант | обычный год | плохой год | просадка | последние 12 мес | 2026 | сделок ⚡ за год — медиана {K} прогонов (мин … макс), [лучше «без добора»]", flush=True)
    for v in V:
        cell = []
        for q in ("p50", "p10", "dd", "last12", "y26"):
            a = np.array(S[v][q]); b = np.array(S[c][q])
            cell.append(f"{np.median(a) * 100:.0f}% [{int((a < b).sum())}]" if q == "dd" else f"${np.median(a):,.0f} (${a.min():,.0f} … ${a.max():,.0f}) [{int((a > b).sum())}]")
        print(f"{v} | " + " | ".join(cell) + f" | {np.median(S[v]['fills']):.0f}", flush=True)
    json.dump(S, open(f"{M.ST}/wf/money_add.json", "w"), indent=1)
    print("money add done", flush=True)
