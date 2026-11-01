"""the model-picked short breakout (rbs_ml.py: 4h, the hold <= 2 days) into the Binance bundle by the strictest money
(money_arm2.run, the bot's settings at 17x, ⚡ + P/R + SMC + EMA + HTF): its walk-forward trades 2023-2026 (each year's
model trained on the years before) at 1 / 2% -> the 144 windows' table vs the bundle without it"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]   # money_arm2 reads sys.argv at import
import lightgbm as lgb
import money_arm2 as MA2, money_multi as M, money_expect as X, money_params as MP, money_rbx as RB, rbs_ml as ML
from multiprocessing import Pool
VARS = {"A: стоп 1.5, тейк 2R, >0.8": (1.5, "t2", 2, 0.8), "B: стоп 1.5, тейк 3R, >0.6": (1.5, "t3", 2, 0.6), "C: стоп 2, тейк 2R, >0.8": (2.0, "t2", 2, 0.8)}
RISK = (1.0, 2.0); TFH = 4; SEEDS = (1, 2)


def trades(sk, xn, hd, th):
    z = dict(np.load(f"{ML.ST}/wf/rbs_{TFH}.npz")); Xf = np.load(f"{ML.ST}/wf/rbs_{TFH}_X.npz")["X"]
    si, xi, hi = ML.STOPS.index(sk), ML.EXITS.index(xn), ML.HOLDS.index(hd)
    r = z["y"][:, si, xi, hi, 0]; b = z["y"][:, si, xi, hi, 1]; t = z["t"]; ok = np.isfinite(r); yr = ML.year(t)
    pred = np.full(len(t), np.nan)
    for Y in ML.TEST:
        tr = ok & (t < ML.ystart(Y) - hd * 86400); te = ok & (yr == Y)
        pred[te] = lgb.train(dict(ML.P, num_threads=4), lgb.Dataset(Xf[tr], np.clip(r[tr], -1.5, 4.0)), num_boost_round=300).predict(Xf[te])
    sel = np.flatnonzero(ok & np.isfinite(pred) & (pred > th))
    sel = sel[ML.dedupe(z["sym"][sel], t[sel], b[sel], TFH)]
    out = [{"t0": int(t[k]), "t1": int(t[k] + b[k] * TFH * 3600), "r": float(r[k]) - 0.03, "st": float(sk * z["atr"][k] / z["e"][k]),
            "sth": float(sk * z["atr"][k] / z["e"][k]), "mod": "rbs", "sym": str(z["sym"][k]), "side": int(z["side"][k]), "e": float(z["e"][k]), "stream": None}
           for k in sel]
    return out


_D = {}
def _init(D): _D.update(D)
def job(a):
    v, rk, sd, A = a
    OT = _D["ot"] + (_D[v] if rk else [])
    return v, rk, sd, A, MA2.run(_D["or"], OT, A, A + 365 * 86400, RB.F, sd, rk=dict(MP.rk(emx=3.0), rbs=rk or 0.0))


if __name__ == "__main__":
    D = {"or": MA2.orders(), "ot": [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]}
    for v, p in VARS.items():
        D[v] = trades(*p); rs = np.array([x["r"] for x in D[v]])
        print(f"{v}: {len(rs)} сделок, {rs.mean():+.3f}R (после 0.03R трения), {len(rs) / (3.83 * 52):.1f}/нед", flush=True)
    jobs = [(v, 0, sd, A) for v in list(VARS)[:1] for sd in SEEDS for A in X.STARTS] + [(v, rk, sd, A) for v in VARS for rk in RISK for sd in SEEDS for A in X.STARTS]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, jobs, chunksize=6)
    R = {}
    for v, rk, sd, A, x in res: R.setdefault((v if rk else "base", rk), {}).setdefault(A, []).append(x)
    b = np.array([np.mean([x[0] for x in R[("base", 0)][A]]) for A in X.STARTS])
    print(f"без пробоя: плохой ${np.percentile(b, 10):,.0f} обычный ${np.median(b):,.0f} просадка {np.median([np.mean([x[1] for x in R[('base', 0)][A]]) for A in X.STARTS]) * 100:.0f}%", flush=True)
    for v in VARS:
        for rk in RISK:
            E = np.array([np.mean([x[0] for x in R[(v, rk)][A]]) for A in X.STARTS]); dd = np.array([np.mean([x[1] for x in R[(v, rk)][A]]) for A in X.STARTS])
            print(f"{v} {rk:g}%: плохой ${np.percentile(E, 10):,.0f} обычный ${np.median(E):,.0f} просадка {np.median(dd) * 100:.0f}% лучше в {int((E > b * 1.001).sum())}/{len(b)}", flush=True)
    print("money rbs done", flush=True)
