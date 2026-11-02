"""a plan of the balance month by month (the user: "расчет примерно по месяцам с дополнениями по 100$ 6 месяцев на год вперёд
стартуя с 200"): the bot as it trades from v0.99.768 (money_hdr2's config: 3 streams, the liquidity cut, the impact), a start of
EQ0 and DEP every 30 days N times; the 144 one-year windows (the bad 1-in-10 / the median / the good 1-in-10 of each month's
balance, before that month's top-up) + the last 12 months, the median of K runs dropping 5% of the trades.
usage: ALLSUF=_clr money_plan.py EQ0 DEP N [K]"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
EQ0, DEP, N = float(ARGV[0]), float(ARGV[1]), int(ARGV[2]); K = int(ARGV[3]) if len(ARGV) > 3 else 4
RULE = f"Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125|slip=1|liq=4:0.5/8:0.25/12:0|path=1" + (f"|dep={DEP:g}/30/{N}" if N else "")
_D = {}
def _init(D): _D.update(D)
def job(a):
    k, A = a
    return k, A, MA2.run(_D[(k, "or")], _D[(k, "ot")], A, A + 365 * 86400, RULE, 1, eq0=EQ0)
if __name__ == "__main__":
    base = MA2.orders(); o2 = [dict(o, xm=0.75) for o in MA2.stream_orders("wick4h_o2", "") if o["prio"] >= 1.05]
    OT = [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]; D = {}
    for k in range(K):
        rng = np.random.default_rng(300 + k)
        D[(k, "or")] = sorted([o for o in base + o2 if rng.random() >= 0.05], key=lambda o: o["t"]); D[(k, "ot")] = [v for v in OT if rng.random() >= 0.05]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, [(k, A) for k in range(K) for A in X.STARTS + [X.LAST]], chunksize=6)
    R = {(k, A): r for k, A, r in res}
    print(f"старт ${EQ0:,.0f} + по ${DEP:,.0f} каждые 30 дней {N} раз (внесено ${EQ0 + DEP * N:,.0f})", flush=True)
    print("месяц | плохой (1 из 10) | обычный | хороший (1 из 10) | последние 12 мес", flush=True)
    out = []
    for m in range(13):
        q = lambda f: np.median([f(np.array([R[(k, A)][4][m] for A in X.STARTS])) for k in range(K)])
        row = (q(lambda x: np.percentile(x, 10)), q(np.median), q(lambda x: np.percentile(x, 90)), np.median([R[(k, X.LAST)][4][m] for k in range(K)]))
        out.append([float(x) for x in row])
        print(f"{m + 1 if m < 12 else 'итог'} | ${row[0]:,.0f} | ${row[1]:,.0f} | ${row[2]:,.0f} | ${row[3]:,.0f}", flush=True)
    dd = np.median([np.median([R[(k, A)][1] for A in X.STARTS]) for k in range(K)])
    print(f"просадка (на долю, пополнения её не прячут): обычная {dd * 100:.0f}%", flush=True)
    json.dump(out, open(f"{M.ST}/wf/money_plan_{int(EQ0)}_{int(DEP)}_{N}.json", "w"))
    print("money plan done", flush=True)
