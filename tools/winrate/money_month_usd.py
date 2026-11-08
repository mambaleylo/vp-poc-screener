"""The month's profit in $ by the balance (the user: "с какой суммы на балансе в месяц получается плюсом 3000$?"): the bot as it
trades since v0.99.775 (the header's money: the strictest rule, the liquidity cut, the slippage — the cut grows with the
balance), 30-day windows started every week 2023-01 .. 2026-09 from each balance, K noise runs: the median month's $, the
25% / 75% months, the share of losing months, the share of months with >= $3000.
usage: ALLSUF=_clr money_month_usd.py [K]"""
import sys, os, json, zlib, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
RULE = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125|slip=1|liq=4:0.5/8:0.25/12:0|dlm=4|prv=3.75|smc=3.125|emx=3.75|htf=2.5|cfl=2|cflheat=0.45"
K = int(ARGV[0]) if ARGV else 2
BAL = (1000, 2000, 3000, 5000, 7500, 10000, 20000, 50000)
W = list(range(X.STARTS[0] - 4 * 7 * 86400, X.LAST + 330 * 86400, 7 * 86400))
_D = {}
def _init(D): _D.update(D)
def job(a):
    b, k, A = a
    return b, k, A, MA2.run(_D[("or", k)], _D[("ot", k)], A, A + 30 * 86400, RULE, 1, eq0=float(b))[0] - b
if __name__ == "__main__":
    base = MA2.orders(); o2 = [dict(o, xm=0.75) for o in MA2.stream_orders("wick4h_o2", "") if o["prio"] >= 1.05]
    OR = sorted(base + o2, key=lambda o: o["t"]); OT = [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf_cfl"] - {"dlm"}]; D = {}
    tmax = max(o["t"] for o in OR); W = [A for A in W if A + 30 * 86400 <= tmax]
    for k in range(K):
        rng = np.random.default_rng(300 + k); D[("or", k)] = [o for o in OR if rng.random() >= 0.05]
        D[("ot", k)] = [v for v in OT if zlib.crc32(f"{k}|{v['mod']}|{v['sym']}|{v['side']}|{v['t0']}".encode()) % 100 >= 5]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, [(b, k, A) for b in BAL for k in range(K) for A in W], chunksize=8)
    by = {}
    for b, k, A, p in res: by.setdefault(b, []).append(p)
    print(f"окон по 30 дней: {len(W)} x {K} прогона", flush=True)
    print("баланс | месяц: медиана | 25% худших ниже | 25% лучших выше | месяцев в минусе | месяцев с +$3000 и больше", flush=True)
    out = {}
    for b in BAL:
        p = np.array(by[b]); out[b] = {"p50": float(np.median(p)), "p25": float(np.percentile(p, 25)), "p75": float(np.percentile(p, 75)),
                                       "neg": float((p < 0).mean()), "ge3k": float((p >= 3000).mean())}
        o = out[b]
        print(f"${b:,} | {o['p50']:+,.0f} | {o['p25']:+,.0f} | {o['p75']:+,.0f} | {o['neg'] * 100:.0f}% | {o['ge3k'] * 100:.0f}%", flush=True)
    json.dump(out, open(f"{M.ST}/wf/money_month_usd.json", "w"), indent=1)
    print("month usd done", flush=True)
