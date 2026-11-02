"""⚡ a third stream on another chart (the user: "какие таймфремы для лимиток ещё можно попробовать" -> the 4h grid shifted by 2 h,
3h, 6h, 8h): each new chart's orders (dlm_build.py BASE_ONLY + dlm_allorders.py: the lab's yearly walk-forward on the bot's
features, the wick 1 ATR rule and the 4h stream's exits) added to the bundle as the bot is (_clr: ⚡ 4h + 2h, P/R, SMC, EMA,
HTF) in the strictest money (money_arm2, the header's rule; Bn is deterministic: one seed): the 144 one-year windows + the
last 12 months + 2026 alone (1 Jan -> 1 Oct); each new stream's fills and R by year first. usage: ALLSUF=_clr money_tf.py"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
RULE = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125"; NEW = (ARGV[0] if ARGV else "wick4h_o2,wick3h,wick6h,wick8h").split(",")
A26, B26 = M.ts(2026, 1, 1), M.ts(2026, 10, 1)
_D = {}
def _init(D): _D.update(D)
def job(a):
    v, A, B = a
    return v, A, B, MA2.run(_D[v], _D["ot"], A, B, RULE, 1)
if __name__ == "__main__":
    base = MA2.orders(); D = {"ot": [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}], "как в боте (4ч + 2ч)": base}
    for st in NEW:
        so = MA2.stream_orders(st, "")
        f = [o for o in so if o["filled"]]
        print(f"{st}: ордеров {len(so)}, исполнено {len(f)}; R по годам " +
              " · ".join(f"{Y} {len(z)} {np.mean(z) if z else 0:+.3f}" for Y in (2023, 2024, 2025, 2026) for z in [[o['r'] for o in f if M.ts(Y) <= o['t'] < M.ts(Y + 1)]]), flush=True)
        D[f"+ {st}"] = sorted(base + so, key=lambda o: o["t"])
    V = [k for k in D if k != "ot"]
    jobs = [(v, A, A + 365 * 86400) for v in V for A in X.STARTS + [X.LAST]] + [(v, A26, B26) for v in V]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, jobs, chunksize=4)
    R = {(v, A, B): r for v, A, B, r in res}
    b = np.array([R[(V[0], A, A + 365 * 86400)][0] for A in X.STARTS]); out = {}
    print("\nвариант | обычный год | плохой | хороший | просадка | последние 12 мес | 2026 (1 янв → 1 окт) | лучше «как в боте» | сделок ⚡ за год", flush=True)
    for v in V:
        e = np.array([R[(v, A, A + 365 * 86400)][0] for A in X.STARTS]); dd = np.array([R[(v, A, A + 365 * 86400)][1] for A in X.STARTS])
        nf = np.mean([R[(v, A, A + 365 * 86400)][2] for A in X.STARTS])
        o = {"p50": float(np.median(e)), "p10": float(np.percentile(e, 10)), "p90": float(np.percentile(e, 90)), "dd": float(np.median(dd)),
             "last12": float(R[(v, X.LAST, X.LAST + 365 * 86400)][0]), "y26": float(R[(v, A26, B26)][0]), "better": int((e > b * 1.001).sum()), "fills": float(nf)}
        out[v] = o
        print(f"{v} | ${o['p50']:,.0f} | ${o['p10']:,.0f} | ${o['p90']:,.0f} | {o['dd'] * 100:.0f}% | ${o['last12']:,.0f} | ${o['y26']:,.0f} | {o['better']}/{len(b)} | {nf:.0f}", flush=True)
    json.dump(out, open(f"{M.ST}/wf/money_tf.json", "w"), indent=1)
    print("money tf done", flush=True)
