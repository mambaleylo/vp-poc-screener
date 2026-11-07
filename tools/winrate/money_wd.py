"""Withdrawals (the user: "система видит, что месяц статистически очень удачный… лучше вывести какое-то количество денег… если
месяц не очень, то вывод замедлит рост — не выводить; предложи лучшие варианты в зависимости от баланса"):
(1) does a great month foretell a fall? Every 30-day month of the yearly windows (no withdrawals): the month's return by
quintile -> the next month's median, the share of a >= 30% fall of the balance within the next 3 months;
(2) the withdrawal rules of money_arm2 (wd=…) from $1k / $3k / $5k / $10k / $100k, a year, every STEP-th weekly window, K noise runs:
the whole money (the account + withdrawn) median / the bad 10%, the withdrawn median, the whole money's drawdown, the share
of the windows ending below the start. The bot as it trades since v0.99.778 (the header's rule).
usage: ALLSUF=_clr money_wd.py K STEP   -> <LABSTORE>/wf/money_wd.json"""
import sys, os, json, zlib, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
RULE = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125|slip=1|liq=4:0.5/8:0.25/12:0|path=1|dlm=4|prv=3.75|smc=3.125|emx=3.75|htf=2.5|cfl=2|cflheat=0.35"
K = int(ARGV[0]) if ARGV else 2; STEP = int(ARGV[1]) if len(ARGV) > 1 else 3; W = X.STARTS[::STEP]
POL = {"none": "",   # each: the wd=… rule [+ wdmin=$ nothing below the balance, wdm0=N nothing in the first N months]
       "p30": "wd=p/0.3|wdmin=10000",                  # 30% of every month in profit, from $10k
       "g100": "wd=g/1.0/0.5",                          # half the profit of a month that doubled, any balance
       "g100m": "wd=g/1.0/0.5|wdmin=10000",             # the same from $10k
       "g50m": "wd=g/0.5/0.5|wdmin=10000",              # half the profit of a +50% month, from $10k
       "h30m": "wd=h/0.3|wdmin=10000",                  # 30% of the gain above the best month-end, from $10k
       "h50m": "wd=h/0.5|wdmin=10000",                  # 50% of it
       "c100k": "wd=c/100000", "c300k": "wd=c/300000",  # the account kept at most $100k / $300k
       "tier": "wd=t/10000:0.2/100000:0.5/300000:0.8",  # above the best: 20% from $10k, 50% from $100k, 80% from $300k
       "tier2": "wd=t/30000:0.3/100000:0.5/300000:0.9|wdm0=3"}
BAL = (1000, 3000, 5000, 10000, 100000)   # the user: "ещё и 3000 и 5000"
_D = {}
def _init(D): _D.update(D)
def job(a):
    nm, b, k, A = a
    r = MA2.run(_D[("or", k)], _D[("ot", k)], A, A + 365 * 86400, RULE + ("|" + POL[nm] if POL[nm] else ""), 1, eq0=float(b))
    w = dict(MA2.WD_LAST) if POL[nm] else {"wd": 0.0, "tdd": r[1], "acct": r[0]}
    return nm, b, k, A, float(r[0]), float(w.get("wd", 0.0)), float(w.get("tdd", r[1])), list(r[4])
if __name__ == "__main__":
    base = MA2.orders(); o2 = [dict(o, xm=0.75) for o in MA2.stream_orders("wick4h_o2", "") if o["prio"] >= 1.05]
    OR = sorted(base + o2, key=lambda o: o["t"]); OT = [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf_cfl"] - {"dlm"}]; D = {}
    for k in range(K):
        rng = np.random.default_rng(300 + k); D[("or", k)] = [o for o in OR if rng.random() >= 0.05]
        D[("ot", k)] = [v for v in OT if zlib.crc32(f"{k}|{v['mod']}|{v['sym']}|{v['side']}|{v['t0']}".encode()) % 100 >= 5]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, [(nm, b, k, A) for nm in POL for b in BAL for k in range(K) for A in W], chunksize=4)
    # (1) the months after a great month (no withdrawals, from $1k)
    mr, nx, fall = [], [], []
    for nm, b, k, A, acct, wd, tdd, path in res:
        if nm != "none" or b != 1000: continue
        P = [float(b)] + [float(x) for x in path[:12]]
        for m in range(1, len(P) - 3):
            if P[m - 1] <= 0 or P[m] <= 0: continue
            mr.append(P[m] / P[m - 1] - 1); nx.append(P[m + 1] / P[m] - 1); fall.append(min(P[m + 1:m + 4]) / P[m] - 1)
    mr, nx, fall = np.array(mr), np.array(nx), np.array(fall); q = np.quantile(mr, [0.2, 0.4, 0.6, 0.8])
    print("(1) месяц (квинтиль) | его доходность | следующий месяц, медиана | падение >= 30% за 3 мес | следующий месяц в плюсе", flush=True)
    stat = []
    for i, (lo, hi) in enumerate(zip([-9] + list(q), list(q) + [1e9])):
        m_ = (mr >= lo) & (mr < hi)
        row = {"q": i + 1, "ret": float(np.median(mr[m_])), "next": float(np.median(nx[m_])), "fall30": float((fall[m_] <= -0.3).mean()), "next_up": float((nx[m_] > 0).mean())}
        stat.append(row)
        print(f"{i + 1} | {row['ret'] * 100:+.0f}% | {row['next'] * 100:+.0f}% | {row['fall30'] * 100:.0f}% | {row['next_up'] * 100:.0f}%", flush=True)
    # (2) the rules
    print("(2) правило | старт | всё (счёт + выведено): медиана | 10% худших | выведено, медиана | просадка всех денег, медиана / 90% | окон ниже старта", flush=True)
    out = {"months": stat, "rules": {}}
    for b in BAL:
        for nm in POL:
            R_ = [(acct + wd, wd, tdd) for n_, b_, k, A, acct, wd, tdd, p in res if n_ == nm and b_ == b]
            tot = np.array([x[0] for x in R_]); wd = np.array([x[1] for x in R_]); dd = np.array([x[2] for x in R_])
            o = {"p50": float(np.median(tot)), "p10": float(np.percentile(tot, 10)), "wd": float(np.median(wd)), "dd": float(np.median(dd)),
                 "dd90": float(np.percentile(dd, 90)), "below": float((tot < b).mean())}
            out["rules"][f"{nm}@{b}"] = o
            print(f"{nm} | ${b:,} | ${o['p50']:,.0f} | ${o['p10']:,.0f} | ${o['wd']:,.0f} | {o['dd'] * 100:.0f}% / {o['dd90'] * 100:.0f}% | {o['below'] * 100:.0f}%", flush=True)
    json.dump(out, open(f"{M.ST}/wf/money_wd.json", "w"), indent=1)
    print("money wd done", flush=True)
