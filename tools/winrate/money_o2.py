"""improving the shifted 4h stream (the user: "попробуй улучши 4ч со сдвигом"): the bundle + the o2 stream as the candidate vs its
variants — o2's risk x0.75 / x0.5 (money_arm2 "xm"), o2's orders above q0.98 (more of them), o2 scored by one model trained
on both 4h grids' orders (wick4h + o2: twice the data), and all three shifted grids (o1, o2, o3) — and the bot as it is; the
money's noise handled as money_tf3: K paired runs each dropping the same random 5% of the shared trades, every 3rd one-year
window + the last 12 months + 2026; the median of the runs (min … max) and the runs where a variant beats the candidate.
usage: ALLSUF=_clr money_o2.py [K]"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
RULE = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125"; K = int(ARGV[0]) if ARGV else 6; DROP = 0.05
A26, B26 = M.ts(2026, 1, 1), M.ts(2026, 10, 1); STARTS = X.STARTS[::3]
_D = {}
def _init(D): _D.update(D)
def job(a):
    v, k, A, B = a
    return v, k, A, B, MA2.run(_D[(v, k)], _D[(k, "ot")], A, B, RULE, 1)
if __name__ == "__main__":
    base = MA2.orders(); OT = [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]
    so = lambda st, suf="": MA2.stream_orders(st, suf)
    o2, o1, o3, o2q, o2m = so("wick4h_o2"), so("wick4h_o1"), so("wick4h_o3"), so("wick4h_o2", "_q0.98"), so("wick4h_o2", "_mix")
    for nm, x in (("o2", o2), ("o1", o1), ("o3", o3), ("o2 q0.98", o2q), ("o2 общая модель", o2m)):
        f = [o["r"] for o in x if o["filled"] and o["t"] >= M.ts(2023)]
        print(f"{nm}: ордеров {len(x)}, исполнено с 2023 {len(f)}, R {np.mean(f):+.3f}", flush=True)
    VARS = {"как в боте": lambda: [], "кандидат: + сдвиг 2ч": lambda: o2, "сдвиг, риск ×0.75": lambda: [dict(o, xm=0.75) for o in o2],
            "сдвиг, риск ×0.5": lambda: [dict(o, xm=0.5) for o in o2], "сдвиг, порог q0.98": lambda: o2q, "сдвиг, общая модель 4ч": lambda: o2m,
            "+ сдвиги 1, 2, 3ч": lambda: o1 + o2 + o3}
    D = {}
    for k in range(K):
        rng = np.random.default_rng(100 + k)
        kb = [o for o in base if rng.random() >= DROP]; D[(k, "ot")] = [v for v in OT if rng.random() >= DROP]
        for v, f in VARS.items():
            r2 = np.random.default_rng(1000 + k)   # the same drop of the added stream across its variants
            D[(v, k)] = sorted(kb + [o for o in f() if r2.random() >= DROP], key=lambda o: o["t"])
    V = list(VARS)
    jobs = [(v, k, A, A + 365 * 86400) for v in V for k in range(K) for A in STARTS + [X.LAST]] + [(v, k, A26, B26) for v in V for k in range(K)]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, jobs, chunksize=4)
    R = {(v, k, A, B): r for v, k, A, B, r in res}
    S = {v: {q: [] for q in ("p50", "p10", "dd", "last12", "y26")} for v in V}
    for v in V:
        for k in range(K):
            e = np.array([R[(v, k, A, A + 365 * 86400)][0] for A in STARTS]); dd = np.array([R[(v, k, A, A + 365 * 86400)][1] for A in STARTS])
            S[v]["p50"].append(float(np.median(e))); S[v]["p10"].append(float(np.percentile(e, 10))); S[v]["dd"].append(float(np.median(dd)))
            S[v]["last12"].append(float(R[(v, k, X.LAST, X.LAST + 365 * 86400)][0])); S[v]["y26"].append(float(R[(v, k, A26, B26)][0]))
    c = V[1]
    print(f"\nвариант | обычный год | плохой год | просадка | последние 12 мес | 2026 — медиана {K} прогонов (мин … макс), [лучше кандидата в прогонах]", flush=True)
    for v in V:
        cell = []
        for q in ("p50", "p10", "dd", "last12", "y26"):
            a = np.array(S[v][q]); b = np.array(S[c][q])
            if q == "dd":
                cell.append(f"{np.median(a) * 100:.0f}% [{int((a < b).sum())}]")
            else:
                cell.append(f"${np.median(a):,.0f} (${a.min():,.0f} … ${a.max():,.0f}) [{int((a > b).sum())}]")
        print(f"{v} | " + " | ".join(cell), flush=True)
    json.dump(S, open(f"{M.ST}/wf/money_o2.json", "w"), indent=1)
    print("money o2 done", flush=True)
