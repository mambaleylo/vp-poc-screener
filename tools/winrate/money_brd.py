"""⚡ with the market-breadth features vs the same recipe without them (run_brd.sh: allorders_<stream>_b0 / _brd of the 4h and
the shifted 4h streams; the 2h stream as deployed, _clr): first the filled orders' R by year, then the bundle's money as the
header counts it (the bot's risks of v0.99.775, the bundle with HTF, a year from $100), K paired runs (⚡'s drop by each order's
hash: the same order dropped in both), every 2nd window + the last 12 months.
usage: ALLSUF=_clr money_brd.py [K]   -> <LABSTORE>/wf/money_brd.json"""
import sys, os, json, zlib, calendar, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
RULE = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125|slip=1|liq=4:0.5/8:0.25/12:0|path=1|dlm=4|prv=3.75|smc=3.125|emx=3.75|htf=2.5"
K = int(ARGV[0]) if ARGV else 4; W = X.STARTS[::2]
ts = lambda y: calendar.timegm((y, 1, 1, 0, 0, 0))
def build(suf):
    o2 = [dict(o, xm=0.75) for o in MA2.stream_orders("wick4h_o2", suf) if o["prio"] >= 1.05]
    return sorted(MA2.stream_orders("wick4h", suf) + MA2.stream_orders("close2h", "_clr") + o2, key=lambda o: o["t"])
V = {"без ширины рынка (рецепт бота)": "_b0", "с шириной рынка": "_brd"}
hk = lambda o, k: zlib.crc32(f"{k}|{o['coin']}|{o['stream']}|{o['side']}|{o['t']}".encode()) % 100 >= 5
_D = {}
def _init(D): _D.update(D)
def job(a):
    nm, k, A = a
    return nm, k, A, MA2.run(_D[("or", nm, k)], _D[("ot", k)], A, A + 365 * 86400, RULE, 1)
if __name__ == "__main__":
    ORS = {nm: build(s) for nm, s in V.items()}
    for nm, OR in ORS.items():
        for st in ("wick4h", "wick4h_o2"):
            f = [o for o in OR if o["stream"] == st and o["filled"]]
            ys = " ".join(f"{Y}: {sum(1 for o in f if ts(Y) <= o['t'] < ts(Y + 1))} {np.mean([o['r'] for o in f if ts(Y) <= o['t'] < ts(Y + 1)]):+.3f}" for Y in range(2023, 2027))
            print(f"{nm} · {st}: исполненных {len(f)}, R {np.mean([o['r'] for o in f]):+.3f} | {ys}", flush=True)
    OT = [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]; D = {}
    for k in range(K):
        D[("ot", k)] = [v for v in OT if zlib.crc32(f"{k}|{v['mod']}|{v['sym']}|{v['side']}|{v['t0']}".encode()) % 100 >= 5]
        for nm, OR in ORS.items(): D[("or", nm, k)] = [o for o in OR if hk(o, k)]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, [(nm, k, A) for nm in V for k in range(K) for A in W + [X.LAST]], chunksize=4)
    R = {(nm, k, A): r for nm, k, A, r in res}; out = {}
    print("вариант | плохой год | обычный | хороший | просадка | худшие 10% окон | последние 12 мес", flush=True)
    for nm in V:
        p10, p50, p90, dd, dd90, l12 = [], [], [], [], [], []
        for k in range(K):
            e = np.array([R[(nm, k, A)][0] for A in W]); d_ = np.array([R[(nm, k, A)][1] for A in W])
            p10.append(np.percentile(e, 10)); p50.append(np.median(e)); p90.append(np.percentile(e, 90)); dd.append(np.median(d_)); dd90.append(np.percentile(d_, 90))
            l12.append(R[(nm, k, X.LAST)][0])
        o = {"p10": int(np.median(p10)), "p50": int(np.median(p50)), "p90": int(np.median(p90)), "dd": int(round(np.median(dd) * 100)),
             "dd90": int(round(np.median(dd90) * 100)), "last12": int(np.median(l12)), "p50_runs": [int(x) for x in p50], "dd_runs": [int(round(x * 100)) for x in dd],
             "l12_runs": [int(x) for x in l12]}
        out[nm] = o
        print(f"{nm} | ${o['p10']:,} | ${o['p50']:,} | ${o['p90']:,} | {o['dd']}% | {o['dd90']}% | ${o['last12']:,} | {o['p50_runs']} {o['dd_runs']}", flush=True)
    json.dump(out, open(f"{M.ST}/wf/money_brd.json", "w"), indent=1, ensure_ascii=False)
    print("money brd done", flush=True)
