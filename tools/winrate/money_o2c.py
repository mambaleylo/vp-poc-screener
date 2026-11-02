"""(money_o2c: the final check of the two improvements found by money_o2 / money_o2b — o2's risk x0.75 and o2's score / threshold
>= 1.05 — alone and together, K paired runs, every 2nd window.) The shifted 4h stream's exits and filters in the money (after o2_screen.py; the user: "поинтереснее гипотезы… фильтры, разные
тейки стопы для 4ч со сдвигом"): the bundle + o2 as the candidate vs o2 with take 2.0 / stop 1.5 ATR, take 1.5 / stop 1.5 (the
orders re-walked on the 1h candles: R, the exit, the stop's distance for the sizing), o2 only where the standard grid's order of
the coin & side stands (a repeat), o2 with score / threshold >= 1.05, and take 2.0 / stop 1.5 + the repeats only. The noise as
money_tf3 (K paired runs dropping the same random 5%, every 3rd window + the last 12 months + 2026). usage: ALLSUF=_clr money_o2c.py [K]"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X, dlm_engine as DE
from multiprocessing import Pool
RULE = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125"; K = int(ARGV[0]) if ARGV else 6; DROP = 0.05
A26, B26 = M.ts(2026, 1, 1), M.ts(2026, 10, 1); STARTS = X.STARTS[::2]
_D = {}
def _init(D): _D.update(D)
def job(a):
    v, k, A, B = a
    return v, k, A, B, MA2.run(_D[(v, k)], _D[(k, "ot")], A, B, RULE, 1)
def rewalk(OR, take, soft, hard=3.0):
    out = []; by = {}
    for o in OR: by.setdefault(o["coin"], []).append(o)
    for c, xs in by.items():
        fl, t1h, fill, R, kind, tout = DE.walk("wick4h_o2", DE.load1h(c), np.array([x["t"] for x in xs]), np.array([x["side"] for x in xs]),
                                               np.array([x["lv"] for x in xs]), np.array([x["atr"] for x in xs]), take, soft, hard)
        for k, x in enumerate(xs):
            f = bool(fl[k]); e = float(fill[k]) if f else x["lv"]
            out.append(dict(x, filled=f, t1h=int(t1h[k]), e=e, r=float(R[k]) if f else 0.0, t1=int(tout[k]), st=soft * x["atr"] / e, sth=hard * x["atr"] / e))
    return sorted(out, key=lambda o: o["t"])
if __name__ == "__main__":
    base = MA2.orders(); OT = [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]
    o2 = MA2.stream_orders("wick4h_o2", "")
    std = {}
    for o in base:
        if o["stream"] == "wick4h": std.setdefault((o["coin"], o["side"]), []).append(o["t"])
    for k_ in std: std[k_] = np.array(sorted(std[k_]))
    rep = lambda o: (lambda a: bool(len(a)) and bool(((a <= o["t"]) & (a > o["t"] - 16 * 3600)).any()))(std.get((o["coin"], o["side"]), np.array([])))
    VARS = {"как в боте": [], "кандидат: + сдвиг 2ч": o2, "сдвиг, риск ×0.75": [dict(o, xm=0.75) for o in o2],
            "сдвиг, оценка/порог ≥ 1.05": [o for o in o2 if o["prio"] >= 1.05],
            "сдвиг, ≥ 1.05 и риск ×0.75": [dict(o, xm=0.75) for o in o2 if o["prio"] >= 1.05]}
    for v, x in VARS.items():
        f = [o["r"] for o in x if o["filled"] and o["t"] >= M.ts(2023)]
        if f: print(f"{v}: исполнено с 2023 {len(f)}, R {np.mean(f):+.3f}", flush=True)
    D = {}
    for k in range(K):
        rng = np.random.default_rng(100 + k)
        kb = [o for o in base if rng.random() >= DROP]; D[(k, "ot")] = [v for v in OT if rng.random() >= DROP]
        drop = {id(o) for o in o2 if np.random.default_rng(hash((k, o["coin"], o["t"], o["side"])) % 2 ** 32).random() < DROP}
        key = lambda o: (o["coin"], o["t"], o["side"]); dk = {key(o) for o in o2 if id(o) in drop}   # the same o2 orders dropped in every variant
        for v, x in VARS.items():
            D[(v, k)] = sorted(kb + [o for o in x if key(o) not in dk], key=lambda o: o["t"])
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
            cell.append(f"{np.median(a) * 100:.0f}% [{int((a < b).sum())}]" if q == "dd" else f"${np.median(a):,.0f} (${a.min():,.0f} … ${a.max():,.0f}) [{int((a > b).sum())}]")
        print(f"{v} | " + " | ".join(cell), flush=True)
    json.dump(S, open(f"{M.ST}/wf/money_o2c.json", "w"), indent=1)
    print("money o2c done", flush=True)
