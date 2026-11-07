"""🔄 Классика in the bundle's money (the user: "надо его взять в работу"): the bundle with HTF as the bot trades it since
v0.99.775 (the strictest rule, the liquidity cut, the slippage, the risks ⚡ 4 / P/R 3.75 / SMC 3.125 / EMA 3.75 / HTF 2.5)
without Классика vs + each variant list of cfl_var.py at a risk (name@risk, e.g. base@1, dr14@2). K paired runs (⚡'s drop by
the rng as money_hdr2, the others by each trade's hash), every STEP-th weekly window + the last 12 months: the bad / usual /
good year, the drawdown, the worst-10% windows' drawdown, the last 12 months, the share of windows below the start at 6 months.
usage: ALLSUF=_clr money_cfl.py K STEP none base@1 …   -> <LABSTORE>/wf/money_cfl.json"""
import sys, os, json, zlib, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
RULE = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125|slip=1|liq=4:0.5/8:0.25/12:0|path=1|dlm=4|prv=3.75|smc=3.125|emx=3.75|htf=2.5"
K = int(ARGV[0]); STEP = int(ARGV[1]); NAMES = ARGV[2:]; W = X.STARTS[::STEP]
hk = lambda v, k: zlib.crc32(f"{k}|{v['mod']}|{v['sym']}|{v['side']}|{v['t0']}".encode()) % 100 >= 5
def cfl_list(nm):
    if nm == "none": return [], 0.0
    v, rk = nm.split("#")[0].split("@")
    out = []
    for x in json.load(open(f"{M.ST}/wf/cfl_var_{v}.json")):
        s = M.bn(x["sym"])
        if s: out.append(dict(x, sym=s, r=float(x["r"]) - 0.03))
    return out, float(rk)
_D = {}
def _init(D): _D.update(D)
def job(a):
    nm, k, A = a
    ex = f"|cflheat={nm.split('#')[1]}" if "#" in nm else ""   # name@risk#X: Классика on its own room of X x the equity
    return nm, k, A, MA2.run(_D[("or", k)], _D[("ot", nm, k)], A, A + 365 * 86400, RULE + f"|cfl={_D[('rk', nm)]:g}" + ex, 1)
if __name__ == "__main__":
    base = MA2.orders(); o2 = [dict(o, xm=0.75) for o in MA2.stream_orders("wick4h_o2", "") if o["prio"] >= 1.05]
    OR = sorted(base + o2, key=lambda o: o["t"]); OTH = [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]; D = {}
    for k in range(K):
        rng = np.random.default_rng(300 + k); D[("or", k)] = [o for o in OR if rng.random() >= 0.05]
    for nm in NAMES:
        L, rk = cfl_list(nm); D[("rk", nm)] = rk if rk > 0 else 1.0
        if L: print(f"{nm}: {len(L)} сделок Классики, {np.mean([x['r'] for x in L]) + 0.03:+.3f}R", flush=True)
        for k in range(K): D[("ot", nm, k)] = sorted([v for v in OTH + L if hk(v, k)], key=lambda v: v["t0"])
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, [(nm, k, A) for nm in NAMES for k in range(K) for A in W + [X.LAST]], chunksize=4)
    R = {(nm, k, A): r for nm, k, A, r in res}; out = {}
    print("вариант | плохой год | обычный | хороший | просадка | худшие 10% окон | последние 12 мес | ниже старта к 6 мес", flush=True)
    for nm in NAMES:
        p10, p50, p90, dd, dd90, l12, m6b = [], [], [], [], [], [], []
        for k in range(K):
            e = np.array([R[(nm, k, A)][0] for A in W]); d_ = np.array([R[(nm, k, A)][1] for A in W]); m6 = np.array([R[(nm, k, A)][4][5] for A in W])
            p10.append(np.percentile(e, 10)); p50.append(np.median(e)); p90.append(np.percentile(e, 90)); dd.append(np.median(d_)); dd90.append(np.percentile(d_, 90))
            l12.append(R[(nm, k, X.LAST)][0]); m6b.append((m6 < 100).mean() * 100)
        o = {"p10": int(np.median(p10)), "p50": int(np.median(p50)), "p90": int(np.median(p90)), "dd": int(round(np.median(dd) * 100)),
             "dd90": int(round(np.median(dd90) * 100)), "last12": int(np.median(l12)), "m6_below": int(round(np.median(m6b))),
             "p50_runs": [int(x) for x in p50], "dd_runs": [int(round(x * 100)) for x in dd], "l12_runs": [int(x) for x in l12]}
        out[nm] = o
        print(f"{nm} | ${o['p10']:,} | ${o['p50']:,} | ${o['p90']:,} | {o['dd']}% | {o['dd90']}% | ${o['last12']:,} | {o['m6_below']}% | {o['p50_runs']} {o['dd_runs']}", flush=True)
    json.dump(out, open(f"{M.ST}/wf/money_cfl.json", "w"), indent=1)
    print("money cfl done", flush=True)
