"""The weekly chart as a filter (the user: "проверить какие-то гипотезы используя крупный таймфрейм… недельный и выше"): every
trade of the bundle + HTF (⚡ orders _clr, P/R / SMC / EMA / HTF from the bot's list) gets its coin's and BTC's weekly state
at its signal — only the last CLOSED week (Binance weeks: Monday 00:00 UTC), from the lab-store's 1h candles: the close vs
the weekly EMA20 (the trend), the place in the last 12 weeks' range. The rules are fixed in advance (no threshold tuned):
  trend_coin      no trade against the coin's weekly trend (a long under its weekly EMA20 / a short above)
  trend_coin_half the risk x0.5 against it
  trend_btc       no trade against BTC's weekly trend;  trend_btc_half — x0.5
  dlm_trend_coin  only ⚡'s orders filtered by the coin's trend (the other modules as they are)
  no_extreme      no long in the top 10% of the 12-week range, no short in the bottom 10%
The strictest money (money_arm2, the header's rule; the Bn rule is deterministic: one seed), the 144 one-year windows + the
last 12 months; the windows by their start year (2023 / 2024 / 2025) to see it hold. usage: ALLSUF=_clr money_wk.py"""
import sys, os, json, bisect, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
RULE = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125"; WEEK = 7 * 86400; MON = 4 * 86400   # 1970-01-05 was a Monday
_W = {}
def weekly(sym):
    """the weekly closes, EMA20, the 12-week high / low by the week's index (the closed weeks only)"""
    if sym not in _W:
        fn = os.path.join(M.ST, "data", "1h", f"{sym}.csv.gz")
        if not os.path.exists(fn):
            _W[sym] = None; return None
        a = np.loadtxt(fn, delimiter=",", ndmin=2, usecols=(0, 2, 3, 4))
        wk = (a[:, 0].astype(np.int64) - MON) // WEEK
        st = np.flatnonzero(np.r_[True, wk[1:] != wk[:-1]]); en = np.r_[st[1:], len(wk)]
        K = wk[st]; C = a[en - 1, 3]; H = np.maximum.reduceat(a[:, 1], st); L = np.minimum.reduceat(a[:, 2], st)
        E = np.empty(len(C)); E[0] = C[0]
        for i in range(1, len(C)): E[i] = E[i - 1] + 2 / 21 * (C[i] - E[i - 1])
        H12 = np.array([H[max(0, i - 11): i + 1].max() for i in range(len(H))]); L12 = np.array([L[max(0, i - 11): i + 1].min() for i in range(len(L))])
        _W[sym] = (K, C, E, H12, L12)
    return _W[sym]
def state(sym, t):
    """at time t: (trend +1 / -1 / 0 unknown, the place in the 12-week range 0..1 or None) of the last closed week"""
    w = weekly(sym)
    if w is None: return 0, None
    K, C, E, H12, L12 = w; k = (int(t) - MON) // WEEK - 1; i = bisect.bisect_right(K, k) - 1
    if i < 20 or K[i] != k: return 0, None   # 20 weeks for the EMA; the last closed week must be there
    tr = 1 if C[i] > E[i] else -1
    pos = (C[i] - L12[i]) / (H12[i] - L12[i]) if H12[i] > L12[i] else 0.5
    return tr, pos
def tag(v, t):
    c, pos = state(v["sym"], t); b, _ = state("BTCUSDT", t)
    return dict(v, w_c=c * v["side"], w_b=b * v["side"], w_pos=pos)
VARS = {
    "как в боте": lambda v: v,
    "по недельному тренду монеты": lambda v: None if v["w_c"] < 0 else v,
    "против тренда монеты риск ×0.5": lambda v: dict(v, xm=0.5) if v["w_c"] < 0 else v,
    "по недельному тренду BTC": lambda v: None if v["w_b"] < 0 else v,
    "против тренда BTC риск ×0.5": lambda v: dict(v, xm=0.5) if v["w_b"] < 0 else v,
    "⚡ по тренду монеты (остальные как есть)": lambda v: None if v["mod"] == "dlm" and v["w_c"] < 0 else v,
    "не у края 12-недельного диапазона": lambda v: None if v["w_pos"] is not None and (v["w_pos"] > 0.9 if v["side"] > 0 else v["w_pos"] < 0.1) else v,
}
_D = {}
def _init(D): _D.update(D)
def job(a):
    v, A = a
    return v, A, MA2.run(_D[v + "|or"], _D[v + "|ot"], A, A + 365 * 86400, RULE, 1)
if __name__ == "__main__":
    OR = [tag(o, o["t"]) for o in MA2.orders()]
    OT = [tag(v, v["t0"]) for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]
    D = {}
    fo = [o for o in OR if o["filled"]] + OT
    for nm, key in (("тренд монеты", "w_c"), ("тренд BTC", "w_b")):
        for s, lab in ((1, "по тренду"), (-1, "против")):
            for mod in ("dlm", "prv", "smc", "emx", "htf"):
                r = [o["r"] for o in fo if o["mod"] == mod and o[key] == s and (o.get("t0") or o["t"]) >= M.ts(2023)]
                print(f"  {nm} {lab} {mod}: {len(r)} сделок, R {np.mean(r) if r else 0:+.3f}", flush=True)
    for v, f in VARS.items():
        D[v + "|or"] = [x for x in (f(o) for o in OR) if x]; D[v + "|ot"] = [x for x in (f(o) for o in OT) if x]
        print(f"{v}: ⚡ ордеров {len(D[v + '|or'])}/{len(OR)}, других сделок {len(D[v + '|ot'])}/{len(OT)}", flush=True)
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, [(v, A) for v in VARS for A in X.STARTS + [X.LAST]], chunksize=4)
    R = {}
    for v, A, r in res: R[(v, A)] = r
    base = np.array([R[("как в боте", A)][0] for A in X.STARTS]); yrs = np.array([int(np.datetime64(A, "s").astype("datetime64[Y]").astype(int) + 1970) for A in X.STARTS])
    out = {}
    print("\nвариант | обычный год | плохой (1 из 10) | хороший | просадка медиана | последние 12 мес | лучше «как в боте» | по годам старта 2023 / 2024 / 2025 (медиана)", flush=True)
    for v in VARS:
        e = np.array([R[(v, A)][0] for A in X.STARTS]); dd = np.array([R[(v, A)][1] for A in X.STARTS])
        o = {"p50": float(np.median(e)), "p10": float(np.percentile(e, 10)), "p90": float(np.percentile(e, 90)), "dd": float(np.median(dd)),
             "last12": float(R[(v, X.LAST)][0]), "better": int((e > base * 1.001).sum()), "by_year": {int(y): float(np.median(e[yrs == y])) for y in (2023, 2024, 2025)}}
        out[v] = o
        print(f"{v} | ${o['p50']:,.0f} | ${o['p10']:,.0f} | ${o['p90']:,.0f} | {o['dd'] * 100:.0f}% | ${o['last12']:,.0f} | {o['better']}/{len(base)} | "
              + " / ".join(f"${o['by_year'][y]:,.0f}" for y in (2023, 2024, 2025)), flush=True)
    json.dump(out, open(f"{M.ST}/wf/money_wk.json", "w"), indent=1)
    print("money wk done", flush=True)
