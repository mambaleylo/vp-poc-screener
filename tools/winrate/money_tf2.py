"""⚡ the shifted 4h grid (wick4h_o2) checked before the bot (the user: "сначала доппроверки, а ещё вдруг 4 + 4 со сдвигом без 2ч
лучше… самое главное, чтобы потом не было так, что… шапку надо опять резать"): the strictest money (money_arm2, the header's
rule, one seed — Bn is deterministic) for the stream combos, the 144 one-year windows by their start year (2023 / 2024 / 2025),
the last 12 months, 2026 alone; every stream's filled R by year on the train coins vs the check coins (never trained on).
usage: ALLSUF=_clr money_tf2.py"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
RULE = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125"; A26, B26 = M.ts(2026, 1, 1), M.ts(2026, 10, 1)
_D = {}
def _init(D): _D.update(D)
def job(a):
    v, A, B = a
    return v, A, B, MA2.run(_D[v], _D["ot"], A, B, RULE, 1)
if __name__ == "__main__":
    suf = os.environ.get("ALLSUF", "")
    S = {"4ч": MA2.stream_orders("wick4h", suf), "2ч": MA2.stream_orders("close2h", suf), "4ч сдвиг": MA2.stream_orders("wick4h_o2", "")}
    Z = {st: np.load(f"{M.ST}/wf/allorders_{f}.npz", allow_pickle=True) for st, f in (("4ч", "wick4h" + suf), ("2ч", "close2h" + suf), ("4ч сдвиг", "wick4h_o2"))}
    print("R исполненных по годам: обучающие монеты | проверочные (модель их не видела)", flush=True)
    for st, z in Z.items():
        f = z["filled"].astype(bool); g = z["grp"].astype(str); t = z["t"]; R = z["R"]
        line = []
        for Y in (2023, 2024, 2025, 2026):
            y = f & (t >= M.ts(Y)) & (t < M.ts(Y + 1))
            a, b = R[y & (g == "train")], R[y & (g == "check")]
            line.append(f"{Y}: {len(a)} {a.mean() if len(a) else 0:+.3f} | {len(b)} {b.mean() if len(b) else 0:+.3f}")
        print(f"  {st}: " + " · ".join(line), flush=True)
    comb = {"как в боте (4ч + 2ч)": ("4ч", "2ч"), "4ч + 2ч + 4ч сдвиг": ("4ч", "2ч", "4ч сдвиг"), "4ч + 4ч сдвиг (без 2ч)": ("4ч", "4ч сдвиг"),
            "4ч сдвиг + 2ч (вместо 4ч)": ("4ч сдвиг", "2ч")}
    D = {"ot": [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]}
    for v, ks in comb.items(): D[v] = sorted([o for k in ks for o in S[k]], key=lambda o: o["t"])
    V = list(comb)
    jobs = [(v, A, A + 365 * 86400) for v in V for A in X.STARTS + [X.LAST]] + [(v, A26, B26) for v in V]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, jobs, chunksize=4)
    R = {(v, A, B): r for v, A, B, r in res}; yr = lambda v, A: R[(v, A, A + 365 * 86400)]
    yrs = np.array([int(str(np.datetime64(A, "s"))[:4]) for A in X.STARTS]); b = np.array([yr(V[0], A)[0] for A in X.STARTS]); out = {}
    print("\nвариант | обычный год | плохой | хороший | просадка медиана / плохое окно | последние 12 мес | 2026 | лучше «как в боте» | по годам старта 2023 / 2024 / 2025 (медиана) | сделок ⚡ за год", flush=True)
    for v in V:
        e = np.array([yr(v, A)[0] for A in X.STARTS]); dd = np.array([yr(v, A)[1] for A in X.STARTS]); nf = np.mean([yr(v, A)[2] for A in X.STARTS])
        o = {"p50": float(np.median(e)), "p10": float(np.percentile(e, 10)), "p90": float(np.percentile(e, 90)), "dd": float(np.median(dd)), "dd90": float(np.percentile(dd, 90)),
             "last12": float(yr(v, X.LAST)[0]), "y26": float(R[(v, A26, B26)][0]), "better": int((e > b * 1.001).sum()),
             "by_year": {int(y): float(np.median(e[yrs == y])) for y in (2023, 2024, 2025)}, "fills": float(nf)}
        out[v] = o
        print(f"{v} | ${o['p50']:,.0f} | ${o['p10']:,.0f} | ${o['p90']:,.0f} | {o['dd'] * 100:.0f}% / {o['dd90'] * 100:.0f}% | ${o['last12']:,.0f} | ${o['y26']:,.0f} | "
              f"{o['better']}/{len(b)} | " + " / ".join(f"${o['by_year'][y]:,.0f}" for y in (2023, 2024, 2025)) + f" | {nf:.0f}", flush=True)
    json.dump(out, open(f"{M.ST}/wf/money_tf2.json", "w"), indent=1)
    print("money tf2 done", flush=True)
