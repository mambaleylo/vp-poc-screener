"""⚡ 2h in the bundle (the user: "сразу мне кажется что только лонги будут лучше на 2ч"): the strictest money (money_arm2, the
header's rule, the bundle + HTF) with the _clr orders (⚡ 4h = the lab's yearly walk-forward, 2h = the deployed recipe's yearly
walk-forward on the restored engine — every year scored by a model trained on the years before: out of sample) three ways:
as the bot is (the 2h shorts at x0.5 already), without 2h, 2h longs only. 1) the header's 144 one-year windows (starts
2023-02 .. 2025-10) + the last 12 months; 2) 2026 alone: a start every week 2026-01-01 .. 2026-07-01, the end 2026-10-01.
usage: ALLSUF=_clr money_2h.py [seeds] -> <LABSTORE>/wf/money_2h.json"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
RULE = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125"; SEEDS = [int(x) for x in (ARGV[0] if ARGV else "1,2").split(",")]
VARS = {"как в боте": lambda o: True, "без ⚡ 2ч": lambda o: o["stream"] != "close2h",
        "⚡ 2ч только лонги": lambda o: o["stream"] != "close2h" or o["side"] > 0}
E26 = M.ts(2026, 10, 1); S26 = list(range(M.ts(2026, 1, 1), M.ts(2026, 7, 1) + 1, 7 * 86400))
_D = {}
def _init(D): _D.update(D)
def job(a):
    v, sd, A, B = a
    return v, sd, A, B, MA2.run(_D[v], _D["ot"], A, B, RULE, sd)
if __name__ == "__main__":
    OR = MA2.orders(); D = {"ot": [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]}
    for v, f in VARS.items():
        D[v] = [o for o in OR if f(o)]
        c2 = [o for o in D[v] if o["stream"] == "close2h" and o["filled"]]
        print(f"{v}: ⚡ ордеров {len(D[v])}, 2ч исполнено {len(c2)}" + (f", R {np.mean([o['r'] for o in c2]):+.3f}" if c2 else ""), flush=True)
    c2 = [o for o in OR if o["stream"] == "close2h" and o["filled"]]
    for Y in (2023, 2024, 2025, 2026):
        y_ = [o for o in c2 if M.ts(Y) <= o["t"] < M.ts(Y + 1)]
        for s, nm in ((1, "лонги"), (-1, "шорты")):
            z = [o["r"] for o in y_ if o["side"] == s]
            print(f"  2ч {Y} {nm}: {len(z)} сделок, R {np.mean(z) if z else 0:+.3f}, сумма {sum(z):+.0f}R", flush=True)
    jobs = [(v, sd, A, A + 365 * 86400) for v in VARS for sd in SEEDS for A in X.STARTS + [X.LAST]] + \
           [(v, sd, A, E26) for v in VARS for sd in SEEDS for A in S26]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, jobs, chunksize=4)
    R = {}
    for v, sd, A, B, r in res: R.setdefault((v, A, B), []).append(r)
    yr = lambda v, A: R[(v, A, A + 365 * 86400)]
    out = {}
    base = np.array([np.mean([x[0] for x in yr("как в боте", A)]) for A in X.STARTS])
    b26 = np.array([np.mean([x[0] for x in R[("как в боте", A, E26)]]) for A in S26])
    print("\nвариант | обычный год | плохой (1 из 10) | хороший | просадка медиана | последние 12 мес | лучше «как в боте» (окон) || "
          "2026: со $100 1 января → 1 октября | просадка | лучше в стартах 2026", flush=True)
    for v in VARS:
        e = np.array([np.mean([x[0] for x in yr(v, A)]) for A in X.STARTS]); dd = np.array([np.mean([x[1] for x in yr(v, A)]) for A in X.STARTS])
        e26 = np.array([np.mean([x[0] for x in R[(v, A, E26)]]) for A in S26]); d26 = np.mean([x[1] for x in R[(v, S26[0], E26)]])
        l12 = np.mean([x[0] for x in yr(v, X.LAST)])
        out[v] = {"p50": float(np.median(e)), "p10": float(np.percentile(e, 10)), "p90": float(np.percentile(e, 90)), "dd": float(np.median(dd)),
                  "last12": float(l12), "better": int((e > base * 1.001).sum()), "y26": float(e26[0]), "dd26": float(d26), "better26": int((e26 > b26 * 1.001).sum()),
                  "y26_all": e26.tolist()}
        o = out[v]
        print(f"{v} | ${o['p50']:,.0f} | ${o['p10']:,.0f} | ${o['p90']:,.0f} | {o['dd'] * 100:.0f}% | ${o['last12']:,.0f} | {o['better']}/{len(base)} || "
              f"${o['y26']:,.0f} | {o['dd26'] * 100:.0f}% | {o['better26']}/{len(S26)}", flush=True)
    json.dump(out, open(f"{M.ST}/wf/money_2h.json", "w"), indent=1)
    print("money 2h done", flush=True)
