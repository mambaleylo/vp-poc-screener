"""A year started on the 1st of every month with top-ups (the user: "таблицы дохода по месяцам за год старт с любого месяца, но
с пополнением на 100 долларов первые полгода, потом таблицу про 3000$ с учётом пополнений"): $100 at the start + $100 after
each of the first 6 months ($700 put in), the bot as it trades since v0.99.775 (the strictest rule, the liquidity cut, the
slippage, the risks ⚡ 4 / P/R 3.75 / SMC 3.125 / EMA 3.75 / HTF 2.5), the median of K noise runs, 2023-01 .. 2025-10 starts:
the balance after 3 / 6 / 12 months, the lowest month-end balance, the drawdown; each month's profit in $ (the month-end
balance less the month's start and its top-up) -> the first month with +$3000 and how many of the 12 had it.
usage: ALLSUF=_clr money_dep_months.py [K]"""
import sys, os, json, zlib, calendar, time, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
RULE = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125|slip=1|liq=4:0.5/8:0.25/12:0|path=1|dep=100/30/6|dlm=4|prv=3.75|smc=3.125|emx=3.75|htf=2.5"
K = int(ARGV[0]) if ARGV else 4
S = [calendar.timegm((y, m, 1, 0, 0, 0)) for y in (2023, 2024, 2025) for m in range(1, 13) if (y, m) <= (2025, 10)]
_D = {}
def _init(D): _D.update(D)
def job(a):
    k, A = a
    return k, A, MA2.run(_D[("or", k)], _D[("ot", k)], A, A + 365 * 86400, RULE, 1)
if __name__ == "__main__":
    base = MA2.orders(); o2 = [dict(o, xm=0.75) for o in MA2.stream_orders("wick4h_o2", "") if o["prio"] >= 1.05]
    OR = sorted(base + o2, key=lambda o: o["t"]); OT = [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]; D = {}
    for k in range(K):
        rng = np.random.default_rng(300 + k); D[("or", k)] = [o for o in OR if rng.random() >= 0.05]
        D[("ot", k)] = [v for v in OT if zlib.crc32(f"{k}|{v['mod']}|{v['sym']}|{v['side']}|{v['t0']}".encode()) % 100 >= 5]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, [(k, A) for k in range(K) for A in S], chunksize=2)
    R = {(k, A): r for k, A, r in res}; out = []
    print("старт | через 3 мес | через 6 мес | худшая точка | через год | просадка | первый месяц с +$3000 | месяцев с +$3000", flush=True)
    for A in S:
        paths = []
        for k in range(K):
            p = list(R[(k, A)][4][:12]); p += [p[-1]] * (12 - len(p)); paths.append(p)
        P = np.median(np.array(paths), axis=0)   # the month-end balances (before that day's top-up)
        prof = []
        for m in range(12):
            prev = 100.0 if m == 0 else P[m - 1] + (100.0 if 1 <= m <= 6 else 0.0)   # the month's start: the last end + the top-up made then
            prof.append(P[m] - prev)
        prof = np.array(prof); first = next((m + 1 for m in range(12) if prof[m] >= 3000), None)
        e = np.median([R[(k, A)][0] for k in range(K)]); dd = np.median([R[(k, A)][1] for k in range(K)])
        row = {"start": time.strftime("%Y-%m", time.gmtime(A)), "m3": float(P[2]), "m6": float(P[5]), "low": float(min([100.0] + list(P))),
               "year": float(e), "dd": float(dd), "first3k": first, "n3k": int((prof >= 3000).sum()), "profit": [round(float(x)) for x in prof]}
        out.append(row)
        print(f"{row['start']} | ${row['m3']:,.0f} | ${row['m6']:,.0f} | ${row['low']:,.0f} | ${row['year']:,.0f} | {dd * 100:.0f}% | "
              f"{('мес ' + str(first)) if first else 'нет'} | {row['n3k']} | {row['profit']}", flush=True)
    json.dump(out, open(f"{M.ST}/wf/money_dep_months.json", "w"), indent=1)
    print("dep months done", flush=True)
