"""📐 EMA improvement round: each variant list of tools/ema_model ema_var.py (<LABSTORE>/wf/ema_var_<name>.json) in place of the
bot's EMA backtest list, judged in the bundle's money as the header counts it (money_hdr2: ⚡ 4h + 2h + the shifted 4h >= 1.05
x0.75, P/R, SMC, EMA; the strictest rule with the liquidity cut and the slippage; a year from $100). Every EMA trade -0.03R like
the other lists' trades. Paired noise: run k drops the same 5% of every list (a trade's hash with k: a trade both variants have
is dropped in both), K runs, the median. "bot" = the EMA list in vp_bt_trades.json as the bot has it now.
usage: ALLSUF=_clr money_ema.py K STEP name…   (STEP: every STEP-th weekly window; -> <LABSTORE>/wf/money_ema.json)"""
import sys, os, json, zlib, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
RULE = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125|slip=1|liq=4:0.5/8:0.25/12:0|path=1"
K = int(ARGV[0]); STEP = int(ARGV[1]); NAMES = ARGV[2:]
MOD = os.environ.get("MOD", "emx")   # the module whose list the variants replace: emx (ema_var.py), smc (smc_var.py) or htf (htf_var.py)
KEEP = {"dlm", "prv", "smc", "emx"} | ({"htf"} if MOD == "htf" else set())   # HTF judged in the header's bundle with HTF
def keep(v, k):   # the paired drop: the same trade -> the same fate in every variant
    return zlib.crc32(f"{k}|{v['mod']}|{v['sym']}|{v['side']}|{v['t0']}".encode()) % 100 >= 5
def var_list(nm):
    if nm == "bot": return [v for v in M.build("base") if v["mod"] == MOD]
    out = []
    fn = f"ema211_var_{nm[4:]}" if nm.startswith("211_") else (f"{MOD}_var_{nm}" if MOD in ("smc", "htf") else f"ema_var_{nm}")   # "211_<name>": the list on the 210 coins (/home/user/ema211)
    for x in json.load(open(f"{M.ST}/wf/{fn}.json")):
        sym = M.bn(x["sym"])
        if sym: out.append(dict(x, sym=sym, r=float(x["r"]) - 0.03))
    return out
_D = {}
def _init(D): _D.update(D)
def job(a):
    nm, k, A = a
    return nm, k, A, MA2.run(_D[("or", k)], _D[("ot", nm, k)], A, A + 365 * 86400, RULE, 1)
if __name__ == "__main__":
    base = MA2.orders(); o2 = [dict(o, xm=0.75) for o in MA2.stream_orders("wick4h_o2", "") if o["prio"] >= 1.05]
    OR = sorted(base + o2, key=lambda o: o["t"])
    OTH = [v for v in M.build("base") if v["mod"] in KEEP - {"dlm", MOD}]
    D = {}
    for k in range(K):
        rng = np.random.default_rng(300 + k); D[("or", k)] = [o for o in OR if rng.random() >= 0.05]
    for nm in NAMES:
        L = var_list(nm); r = np.array([v["r"] for v in L])
        print(f"{nm}: {len(L)} сделок {MOD}, {r.mean() + 0.03:+.3f}R (без −0.03)", flush=True)
        for k in range(K):
            D[("ot", nm, k)] = sorted([v for v in OTH + L if keep(v, k)], key=lambda v: v["t0"])
    W = X.STARTS[::STEP]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, [(nm, k, A) for nm in NAMES for k in range(K) for A in W + [X.LAST]], chunksize=4)
    R = {(nm, k, A): r for nm, k, A, r in res}; out = {}
    for nm in NAMES:
        p50, dd, l12, m6b = [], [], [], []
        for k in range(K):
            e = np.array([R[(nm, k, A)][0] for A in W]); d_ = np.array([R[(nm, k, A)][1] for A in W])
            m6 = np.array([R[(nm, k, A)][4][5] for A in W])
            p50.append(np.median(e)); dd.append(np.median(d_)); l12.append(R[(nm, k, X.LAST)][0]); m6b.append((m6 < 100).mean() * 100)
        out[nm] = {"p50": int(np.median(p50)), "dd": int(round(np.median(dd) * 100)), "last12": int(np.median(l12)), "m6_below": int(round(np.median(m6b))),
                   "p50_runs": [int(x) for x in p50], "last12_runs": [int(x) for x in l12]}
        print(nm, out[nm], flush=True)
    json.dump(out, open(f"{M.ST}/wf/money_{'ema' if MOD == 'emx' else MOD}.json", "w"), indent=1)
    print("money ema done", flush=True)
