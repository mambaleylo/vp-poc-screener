"""The bundle's mix vs the drawdown (the user: "есть какие-то связки с адекватным снижением доходности, но с более выгодными
просадками?"): the deep drawdowns come from ⚡'s clustered trades, the other modules (P/R, SMC, EMA, HTF) draw down little on
their own — so the risk moved from ⚡ to them, ⚡ without a stream, ⚡ off. The header's money (money_hdr2: the strictest rule,
the liquidity cut, the slippage, the bundle with HTF, a year from $100), K paired runs (⚡'s orders drop as money_hdr2, the
others by each trade's hash), every 2nd weekly window + the last 12 months: the usual / bad / good year, the drawdown of the
usual and of the worst-10% window, the share of windows below the start at 6 months.
usage: [ROUND=2] ALLSUF=_clr money_mix.py [K]   -> <LABSTORE>/wf/money_mix[2].json   (ROUND=2: the fine grid around ⚡ 3.5% + x1.25)"""
import sys, os, json, zlib, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
BASE = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125|slip=1|liq=4:0.5/8:0.25/12:0|path=1"; K = int(ARGV[0]) if ARGV else 4
W = X.STARTS[::2]
RK_ = "|dlm=4|prv=3.75|smc=3.125|emx=3.75|htf=2.5"   # the bot's risks since v0.99.775
O = lambda x: f"|prv={3.0 * x:g}|smc={2.5 * x:g}|emx={3.0 * x:g}|htf={2.0 * x:g}"   # the others' risk x x (now 3 / 2.5 / 3 / 2 %)
MIX = {   # name: (the rule's extra, ⚡ streams kept)
    "как сейчас (⚡ 4.5%)": ("", None),
    "⚡ 4%, остальные x1.1": ("|dlm=4.0" + O(1.1), None),
    "⚡ 4%, остальные x1.25": ("|dlm=4.0" + O(1.25), None),
    "⚡ 3.75%, остальные x1.2": ("|dlm=3.75" + O(1.2), None),
    "⚡ 3.5%, остальные x1.1": ("|dlm=3.5" + O(1.1), None),
    "⚡ 3.5%, остальные x1.25": ("|dlm=3.5" + O(1.25), None),
    "⚡ 3.5%, остальные x1.4": ("|dlm=3.5" + O(1.4), None),
    "⚡ 3%, остальные x1.25": ("|dlm=3.0" + O(1.25), None),
    "⚡ 3%, остальные x1.4": ("|dlm=3.0" + O(1.4), None),
} if os.environ.get("ROUND") == "2" else {k_: (RK_ + e_, kp) for k_, (e_, kp) in {   # ROUND=3: the drawdown ideas on the bot's risks
    "как сейчас (риски v0.99.775)": ("", None),
    "1. стоп пачки ⚡ 15% счёта, пауза 24ч": ("|bstop=0.15/24", None),
    "1. стоп пачки ⚡ 25% счёта, пауза 24ч": ("|bstop=0.25/24", None),
    "1. стоп пачки ⚡ 35% счёта, пауза 48ч": ("|bstop=0.35/48", None),
    "2. риск x0.5 при волатильности BTC x2": ("|vol=2.0/0.5", None),
    "2. риск x0.5 при волатильности BTC x3": ("|vol=3.0/0.5", None),
    "3. подтверждение: 4+ в сторону и они < -0.5R": ("|conf=4/0.5", None),
    "3. подтверждение: 6+ в сторону и они < -0.3R": ("|conf=6/0.3", None),
    "4. предел по бете x25 счёта": ("|beta=25", None),
    "4. предел по бете x50 счёта": ("|beta=50", None),
    "5. в просадке 40% риск x0.6": ("|ddc=0.4/0.6/0.25", None),
    "5. в просадке 50% риск x0.5": ("|ddc=0.5/0.5/0.3", None),
    "6. HTF не больше 2 за час": ("|hcap=2", None),
    "6. HTF не больше 3 за час": ("|hcap=3", None),
}.items()} if os.environ.get("ROUND") == "3" else {
    "как сейчас (⚡ 4.5%)": ("", None),
    "⚡ 3.5%": ("|dlm=3.5", None),
    "⚡ 2.5%": ("|dlm=2.5", None),
    "⚡ 3.5%, остальные x1.25": ("|dlm=3.5" + O(1.25), None),
    "⚡ 2.5%, остальные x1.5": ("|dlm=2.5" + O(1.5), None),
    "⚡ 1.5%, остальные x2": ("|dlm=1.5" + O(2.0), None),
    "без ⚡, остальные x2": ("|dlm=0" + O(2.0), None),
    "без ⚡, остальные x3": ("|dlm=0" + O(3.0), None),
    "⚡ без 2ч": ("", ("wick4h", "wick4h_o2")),
    "⚡ без 2ч, остальные x1.5": (O(1.5), ("wick4h", "wick4h_o2")),
}
_D = {}
def _init(D): _D.update(D)
def job(a):
    nm, k, A = a
    ex, keep = MIX[nm]
    OR = _D[("or", k)] if keep is None else [o for o in _D[("or", k)] if o.get("stream", o.get("st")) in keep]
    return nm, k, A, MA2.run(OR, _D[("ot", k)], A, A + 365 * 86400, BASE + ex, 1)
if __name__ == "__main__":
    base = MA2.orders(); o2 = [dict(o, xm=0.75) for o in MA2.stream_orders("wick4h_o2", "") if o["prio"] >= 1.05]
    print("потоки ⚡:", {s: sum(1 for o in base + o2 if o.get("stream", o.get("st")) == s) for s in ("wick4h", "close2h", "wick4h_o2")}, flush=True)
    OT = [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]; D = {}
    for k in range(K):
        rng = np.random.default_rng(300 + k)
        D[("or", k)] = sorted([o for o in base + o2 if rng.random() >= 0.05], key=lambda o: o["t"])
        D[("ot", k)] = [v for v in OT if zlib.crc32(f"{k}|{v['mod']}|{v['sym']}|{v['side']}|{v['t0']}".encode()) % 100 >= 5]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, [(nm, k, A) for nm in MIX for k in range(K) for A in W + [X.LAST]], chunksize=4)
    R = {(nm, k, A): r for nm, k, A, r in res}; out = {}
    print("вариант | плохой год | обычный | хороший | просадка обычная | просадка худших 10% окон | ниже старта к 6 мес | последние 12 мес", flush=True)
    for nm in MIX:
        p10, p50, p90, dd, dd90, m6b, l12 = [], [], [], [], [], [], []
        for k in range(K):
            e = np.array([R[(nm, k, A)][0] for A in W]); d_ = np.array([R[(nm, k, A)][1] for A in W]); m6 = np.array([R[(nm, k, A)][4][5] for A in W])
            p10.append(np.percentile(e, 10)); p50.append(np.median(e)); p90.append(np.percentile(e, 90)); dd.append(np.median(d_))
            dd90.append(np.percentile(d_, 90)); m6b.append((m6 < 100).mean() * 100); l12.append(R[(nm, k, X.LAST)][0])
        o = {"p10": int(np.median(p10)), "p50": int(np.median(p50)), "p90": int(np.median(p90)), "dd": int(round(np.median(dd) * 100)),
             "dd90": int(round(np.median(dd90) * 100)), "m6_below": int(round(np.median(m6b))), "last12": int(np.median(l12)),
             "p50_runs": [int(x) for x in p50], "dd_runs": [int(round(x * 100)) for x in dd]}
        out[nm] = o
        print(f"{nm} | ${o['p10']:,} | ${o['p50']:,} | ${o['p90']:,} | {o['dd']}% | {o['dd90']}% | {o['m6_below']}% | ${o['last12']:,}", flush=True)
    json.dump(out, open(f"{M.ST}/wf/money_mix{os.environ.get('ROUND', '')}.json", "w"), indent=1, ensure_ascii=False)
    print("money mix done", flush=True)
