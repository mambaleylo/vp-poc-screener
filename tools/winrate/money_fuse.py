"""lowering the drawdown without much money lost (the user: "давай изучать новые гипотезы, где можно без особого ущерба для дохода
снизить просадки"): the deep drawdowns (dd_episodes.py) came from many ⚡ positions on one side caught by a sharp market turn
(March 2023 shorts, March 2024 longs). The bot as it trades (money_hdr2's config: 3 streams, the liquidity cut, the impact) vs:
⚡ at most 10 a side; the open risk at the stops <= 70% / 50% of the account; no load multiplier (x1.25 when 5+ ⚡ open); no
new ⚡ short after BTC +4% in 24 h / long after -4%; at most 6 new ⚡ a side in 24 h. K paired runs (the same 5% dropped), every
2nd window + the last 12 months; the usual / bad year, the drawdown in the usual and the bad window, [runs better than the bot].
usage: ALLSUF=_clr money_dd.py [K]"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
BASE = "Bn|arm=0.6|oth=1|dis=1.0|cap=125|slip=1|liq=4:0.5/8:0.25/12:0"; K = int(ARGV[0]) if ARGV else 4; STARTS = X.STARTS[::2]
VARS = {"как в боте": "|heat=1.0", "предохранитель 48ч / −6R": "|heat=1.0|fuse=48/6", "предохранитель 48ч / −10R": "|heat=1.0|fuse=48/10",
        "предохранитель 48ч / −15R": "|heat=1.0|fuse=48/15", "предохранитель 96ч / −10R": "|heat=1.0|fuse=96/10",
        "предохранитель 96ч / −15R": "|heat=1.0|fuse=96/15", "предохранитель 96ч / −25R": "|heat=1.0|fuse=96/25"}
_D = {}
def _init(D): _D.update(D)
def job(a):
    v, k, A = a
    return v, k, A, MA2.run(_D[(k, "or")], _D[(k, "ot")], A, A + 365 * 86400, BASE + VARS[v], 1)
if __name__ == "__main__":
    base = MA2.orders(); o2 = [dict(o, xm=0.75) for o in MA2.stream_orders("wick4h_o2", "") if o["prio"] >= 1.05]
    OT = [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]; D = {}
    for k in range(K):
        rng = np.random.default_rng(300 + k)
        D[(k, "or")] = sorted([o for o in base + o2 if rng.random() >= 0.05], key=lambda o: o["t"]); D[(k, "ot")] = [v for v in OT if rng.random() >= 0.05]
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
    print(f"\nвариант | обычный год | плохой год | просадка обычная | просадка в плохом окне | последние 12 мес — медиана {K} прогонов [лучше бота]", flush=True)
    for v in V:
        cell = []
        for q in ("p50", "p10", "dd", "dd90", "last12"):
            a = np.array(S[v][q]); bb = np.array(b[q]); better = int((a < bb).sum() if q.startswith("dd") else (a > bb).sum())
            cell.append((f"{np.median(a) * 100:.0f}%" if q.startswith("dd") else f"${np.median(a):,.0f}") + f" [{better}]")
        print(f"{v} | " + " | ".join(cell), flush=True)
    json.dump(S, open(f"{M.ST}/wf/money_fuse.json", "w"), indent=1)
    print("money fuse done", flush=True)
