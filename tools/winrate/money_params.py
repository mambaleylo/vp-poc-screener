"""the bundle's risk parameters re-checked on the restored lab (money_expect.py's money: a year from $100, 144 weekly
windows 2023-02..2025-10, 14x, the 2h shorts x0.5, the daily WaveTrend x1.25 at <= -33): the ⚡ load multiplier, the open
risk cap (90%), the ⚡ positions at once (20), ⚡'s risk, the other modules' risks. -> <LABSTORE>/wf/money_params.json"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import money_multi as M, money_expect as X, money_osc as O
from multiprocessing import Pool
RK0 = dict(M.RK)
def rk(**k): d = dict(RK0); d.update(k); return d
VAR = {"сейчас": {},
       "загрузка выкл (x1)": {"load": (5, 1.0, 1.0)}, "загрузка 0.75/1.25": {"load": (5, 0.75, 1.25)}, "загрузка 0.5/1.5": {"load": (5, 0.5, 1.5)},
       "загрузка порог 3": {"load": (3, 0.625, 1.25)}, "загрузка порог 8": {"load": (8, 0.625, 1.25)},
       "лимит риска 70%": {"heat": 0.7}, "лимит риска 80%": {"heat": 0.8}, "лимит риска 100%": {"heat": 1.0}, "лимит риска 120%": {"heat": 1.2},
       "⚡ до 12 сделок": {"side_cap": 12}, "⚡ до 15 сделок": {"side_cap": 15}, "⚡ до 30 сделок": {"side_cap": 30},
       "⚡ 3.5%": {"rk_": rk(dlm=3.5)}, "⚡ 5.5%": {"rk_": rk(dlm=5.5)},
       "P/R 2%": {"rk_": rk(prv=2.0)}, "P/R 4%": {"rk_": rk(prv=4.0)},
       "SMC 1.5%": {"rk_": rk(smc=1.5)}, "SMC 3.5%": {"rk_": rk(smc=3.5)},
       "EMA 1%": {"rk_": rk(emx=1.0)}, "EMA 3%": {"rk_": rk(emx=3.0)},
       "HTF 1%": {"rk_": rk(htf=1.0)}, "HTF 3%": {"rk_": rk(htf=3.0)}}
VAR2 = {"сейчас": {}, "лимит 95%": {"heat": 0.95}, "EMA 3%": {"rk_": rk(emx=3.0)}, "EMA 4%": {"rk_": rk(emx=4.0)},
        "EMA 3% + лимит 95%": {"heat": 0.95, "rk_": rk(emx=3.0)}, "EMA 3% + лимит 100%": {"heat": 1.0, "rk_": rk(emx=3.0)},
        "EMA 3% + P/R 4%": {"rk_": rk(emx=3.0, prv=4.0)}}
SET = sys.argv[1] if len(sys.argv) > 1 else ""
VAR3 = {"сейчас": {}, "EMA 4%": {"rk_": rk(emx=4.0)}, "EMA 5%": {"rk_": rk(emx=5.0)}, "EMA 6%": {"rk_": rk(emx=6.0)},
        "EMA 4% + P/R 4%": {"rk_": rk(emx=4.0, prv=4.0)}, "EMA 4% + SMC 3%": {"rk_": rk(emx=4.0, smc=3.0)}}
if SET == "2": VAR = VAR2
if SET == "3": VAR = VAR3
def job(a):
    nm, A = a
    if "b" not in M._EV: M._EV["b"] = [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"]]
    return nm, A, M.run(M._EV["b"], A, A + 365 * 86400, 14.0, O.W_OSC, eq0=100.0, **VAR[nm])
if __name__ == "__main__":
    with Pool(4) as P:
        res = P.map(job, [(nm, A) for nm in VAR for A in X.STARTS + [X.LAST]], chunksize=6)
    R = {}
    for nm, A, r in res: R.setdefault(nm, {})[A] = r
    b0 = np.array([R["сейчас"][A][0] for A in X.STARTS]); out = {}
    for nm, v in R.items():
        E = np.array([v[A][0] for A in X.STARTS]); dd = np.array([v[A][3] for A in X.STARTS])
        out[nm] = {"p10": int(np.percentile(E, 10)), "p50": int(np.median(E)), "p90": int(np.percentile(E, 90)), "dd": int(round(np.median(dd) * 100)),
                   "dd_max": int(round(dd.max() * 100)), "last12": int(v[X.LAST][0]), "better": int((E > b0 * 1.001).sum()), "q50": float(np.median(E / b0)),
                   "liq": int(sum(v[A][4] for A in X.STARTS))}
        o = out[nm]
        print(f"{nm:22s} плохой ${o['p10']:>6,} обычный ${o['p50']:>7,} хороший ${o['p90']:>8,} просадка {o['dd']}%/{o['dd_max']}% посл.12 ${o['last12']:>8,} | лучше в {o['better']:3d}/144 x{o['q50']:.2f} ликв {o['liq']}", flush=True)
    json.dump(out, open(os.path.join(M.ST, "wf", f"money_params{SET}.json"), "w"), indent=1)
