"""the header and the ⚡ tab's money, re-counted ONCE on the bot as it trades from v0.99.766 (the user: "как закончим с 4ч со
сдвигом и внедрили пересчитаем шапку"): ⚡ 4h + 2h (_clr) + the shifted 4h (score >= 1.05 x thr, risk x0.75), the liquidity
cut 4:0.5/8:0.25/12:0 and the square-root impact of every market fill (slip=1: never in the numbers before), the strictest
money (money_arm2, the header's rule) — ⚡ alone / + P/R, SMC, EMA / + HTF, a year from $100: the 144 weekly windows (2023-02 ..
2025-10) and the last 12 months, the median of K runs each dropping a random 5% of the trades (the money's noise; one path
swings the usual year x2); ⚡ alone also cautious (every trade 0.025R worse), the balance at 6 months.
-> <LABSTORE>/wf/money_hdr2.json. usage: ALLSUF=_clr money_hdr2.py [K]"""
import sys, os, json, zlib, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
RULE = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125|slip=1|liq=4:0.5/8:0.25/12:0|path=1|dlm=4|prv=3.75|smc=3.125|emx=3.75|htf=2.5|cfl=2|cflheat=0.35"; K = int(ARGV[0]) if ARGV else 4   # v0.99.775: the risks (money_mix.py)
_D = {}
def _init(D): _D.update(D)
def job(a):
    kind, k, A = a
    OR = _D[(k, "or_h")] if kind == "dlm_harsh" else _D[(k, "or")]
    OT = [v for v in _D[(k, "ot")] if v["mod"] in X.KINDS["dlm" if kind == "dlm_harsh" else kind]]
    return kind, k, A, MA2.run(OR, OT, A, A + 365 * 86400, RULE, 1)
if __name__ == "__main__":
    base = MA2.orders(); o2 = [dict(o, xm=0.75) for o in MA2.stream_orders("wick4h_o2", "") if o["prio"] >= 1.05]
    OT = [v for v in M.build("base") if v["mod"] != "dlm"]; D = {}
    for k in range(K):
        rng = np.random.default_rng(300 + k)
        D[(k, "or")] = sorted([o for o in base + o2 if rng.random() >= 0.05], key=lambda o: o["t"])
        D[(k, "or_h")] = [dict(o, r=o["r"] - 0.025) for o in D[(k, "or")]]
        # v0.99.774: the other modules' 5% by each trade's own hash (was the same rng after ⚡'s draws: a change of one
        # module's list re-shuffled which trades of the OTHERS were dropped — the bundle without HTF moved $45k -> $53k
        # when only HTF had changed); ⚡'s draw is unchanged (its orders' list)
        D[(k, "ot")] = [v for v in OT if zlib.crc32(f"{k}|{v['mod']}|{v['sym']}|{v['side']}|{v['t0']}".encode()) % 100 >= 5]
    kinds = list(X.KINDS) + ["dlm_harsh"]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, [(kd, k, A) for kd in kinds for k in range(K) for A in X.STARTS + [X.LAST]], chunksize=6)
    R = {(kd, k, A): r for kd, k, A, r in res}; out = {}
    for kd in kinds:
        p10, p50, p90, dd, l12, m6, m6b = [], [], [], [], [], [], []
        for k in range(K):
            e = np.array([R[(kd, k, A)][0] for A in X.STARTS]); d_ = np.array([R[(kd, k, A)][1] for A in X.STARTS])
            m6_ = np.array([R[(kd, k, A)][4][5] for A in X.STARTS])
            p10.append(np.percentile(e, 10)); p50.append(np.median(e)); p90.append(np.percentile(e, 90)); dd.append(np.median(d_))
            l12.append(R[(kd, k, X.LAST)][0]); m6.append(np.median(m6_)); m6b.append((m6_ < 100).mean() * 100)
        out[kd] = {"p10": int(np.median(p10)), "p50": int(np.median(p50)), "p90": int(np.median(p90)), "dd": int(round(np.median(dd) * 100)),
                   "last12": int(np.median(l12)), "m6_median": int(np.median(m6)), "m6_below": int(round(np.median(m6b))),
                   "p50_range": [int(min(p50)), int(max(p50))], "last12_range": [int(min(l12)), int(max(l12))]}
        print(kd, out[kd], flush=True)
    json.dump(out, open(f"{M.ST}/wf/money_hdr2.json", "w"), indent=1)
    print("hdr2 done", flush=True)
