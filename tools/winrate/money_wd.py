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
if len(ARGV) > 2 and ARGV[2] == "lite":   # the user: "300к это же ппц как много… если имея 20к вывести скажем 2000"
    POL = {"none": "", "c300k": "wd=c/300000",
           "b5": "wd=b/0.05|wdmin=20000", "b10": "wd=b/0.1|wdmin=20000", "bh10": "wd=bh/0.1|wdmin=20000",
           "h10": "wd=h/0.1|wdmin=20000", "h20": "wd=h/0.2|wdmin=20000", "f2k": "wd=f/2000|wdmin=20000", "f5k": "wd=f/5000|wdmin=50000"}
BAL = (1000, 3000, 5000, 10000, 100000)   # the user: "ещё и 3000 и 5000"
if len(ARGV) > 2 and ARGV[2] == "best":   # the user: "найди лучшую связку… нормально на жизнь и баланс хорошо рос… через несколько месяцев ощутить деньги"
    POL = {"none": "", "h10_20k": "wd=h/0.1|wdmin=20000",
           "h30_3k": "wd=h/0.3|wdmin=3000", "h50_3k": "wd=h/0.5|wdmin=3000", "h30_5k": "wd=h/0.3|wdmin=5000", "h50_5k": "wd=h/0.5|wdmin=5000",
           "h50_10k": "wd=h/0.5|wdmin=10000", "h70_10k": "wd=h/0.7|wdmin=10000",
           "t_a": "wd=t/3000:0.3/10000:0.5/50000:0.7", "t_b": "wd=t/5000:0.4/20000:0.6/100000:0.8", "t_c": "wd=t/2000:0.2/5000:0.4/20000:0.6"}
    BAL = (1000, 3000, 5000, 10000, 20000)
if len(ARGV) > 2 and ARGV[2] == "combo":   # the best of "best" (30% of the new highs from $5k) + the $5000 a month from $25k
    POL = {"none": "", "h30_5k": "wd=h/0.3|wdmin=5000", "hs30": "wd=hs/0.3/5000/25000|wdmin=5000", "hs50": "wd=hs/0.5/5000/25000|wdmin=5000",
           "hs30_40k": "wd=hs/0.3/5000/40000|wdmin=5000"}
    BAL = (1000, 3000, 5000, 10000, 20000)
if len(ARGV) > 2 and ARGV[2] == "salary":   # the user: "цель — в месяц 5000$ зарабатывать": $5000 out every month from a balance
    POL = {"none": "", "s20k": "wd=s/5000|wdmin=20000", "s30k": "wd=s/5000|wdmin=30000", "s50k": "wd=s/5000|wdmin=50000", "s100k": "wd=s/5000|wdmin=100000"}
    BAL = (1000, 5000, 20000, 30000, 50000, 100000)
_D = {}
def _init(D): _D.update(D)
def job(a):
    nm, b, k, A = a
    r = MA2.run(_D[("or", k)], _D[("ot", k)], A, A + 365 * 86400, RULE + ("|" + POL[nm] if POL[nm] else ""), 1, eq0=float(b))
    w = dict(MA2.WD_LAST) if POL[nm] else {"wd": 0.0, "tdd": r[1], "acct": r[0]}
    return nm, b, k, A, float(r[0]), float(w.get("wd", 0.0)), float(w.get("tdd", r[1])), list(r[4]) + [list(w.get("cum") or []), w.get("m1", 0), w.get("paid", 0)]
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
            if len(ARGV) > 2 and ARGV[2] in ("best", "combo") and nm != "none":   # the withdrawn by the 3rd / 6th / 12th month, the account
                C_ = [p[-3] for n_, b_, k, A, acct, wd_, tdd, p in res if n_ == nm and b_ == b]
                cm = lambda m: np.array([(c[m - 1] if len(c) >= m else (c[-1] if c else 0.0)) for c in C_])
                acc = np.array([acct for n_, b_, k, A, acct, wd_, tdd, p in res if n_ == nm and b_ == b])
                o.update(m3=float(np.median(cm(3))), m6=float(np.median(cm(6))), m6_25=float(np.percentile(cm(6), 25)), m12=float(np.median(cm(12))),
                         m12_25=float(np.percentile(cm(12), 25)), acct=float(np.median(acc)), acct10=float(np.percentile(acc, 10)))
                print(f"   выведено к 3 / 6 / 12 мес: ${o['m3']:,.0f} / ${o['m6']:,.0f} (25% хуже ${o['m6_25']:,.0f}) / ${o['m12']:,.0f} (25% хуже ${o['m12_25']:,.0f}); "
                      f"счёт через год ${o['acct']:,.0f}, 10% худших ${o['acct10']:,.0f}", flush=True)
            if len(ARGV) > 2 and ARGV[2] == "salary" and nm != "none":
                S_ = [(p[-2], p[-1]) for n_, b_, k, A, acct, wd_, tdd, p in res if n_ == nm and b_ == b]
                paid = np.array([x[1] for x in S_]); m1 = np.array([x[0] for x in S_ if x[0]])
                acc = np.array([acct for n_, b_, k, A, acct, wd_, tdd, p in res if n_ == nm and b_ == b])
                o.update(paid=float(np.median(paid)), m1=float(np.median(m1)) if len(m1) else None, never=float((paid == 0).mean()),
                         acct=float(np.median(acc)), acct10=float(np.percentile(acc, 10)))
                print(f"   зарплата: месяцев с $5000 из 12 — медиана {o['paid']:.0f} (ни разу — {o['never'] * 100:.0f}% окон), первый месяц — {o['m1']}, "
                      f"счёт через год — медиана ${o['acct']:,.0f}, 10% худших ${o['acct10']:,.0f}", flush=True)
    json.dump(out, open(f"{M.ST}/wf/money_wd" + ("_" + ARGV[2] if len(ARGV) > 2 else "") + ".json", "w"), indent=1)
    print("money wd done", flush=True)
