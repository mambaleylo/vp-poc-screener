"""the decisions of v0.99.746..749 re-checked with the ⚡ trades of an hour in a random order (5 orders; money_order.py found
the score order the lab used ~25% too kind): the leverage, the 2h shorts cut, the WaveTrend rule, EMA's risk, the open-risk
cap — for the bot's exits (2 / 1.1 ATR) and the candidate (1.75 / 1.2). -> the table + <LABSTORE>/wf/money_recheck.json"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlm_exits as DX, money_multi as M, money_expect as X, money_osc as O, money_params as MP, money_order as MOR
from multiprocessing import Pool
SEEDS = [1, 2, 3, 4, 5]
OLDWT = lambda v: M.W2S(v) * ((1.25 if O.wt_x(v) <= -3 else (0.85 if O.wt_x(v) >= 22 else 1.0)) if v["mod"] == "dlm" else 1.0)
NOW = dict(cap=14.0, wf="osc", heat=0.95, rk=dict(emx=3.0))
VAR = {"сейчас (v0.99.749)": {}, "плечо 10x": {"cap": 10.0}, "плечо 20x": {"cap": 20.0}, "без урезания 2ч-шортов": {"wf": "osc_nocut"},
       "WaveTrend старый": {"wf": "oldwt"}, "без WaveTrend": {"wf": "w2s"}, "EMA 2%": {"rk": {}}, "лимит 90%": {"heat": 0.90}, "лимит 100%": {"heat": 1.0}}
WF = {"osc": O.W_OSC, "w2s": M.W2S, "oldwt": OLDWT, "osc_nocut": lambda v: O.W_OSC(v) / M.W2S(v)}
_E = {}
def _init(E): _E.update(E)
def job(a):
    ex, nm, sd, A = a; p = dict(NOW, **VAR[nm])
    return ex, nm, sd, A, M.run(_E[(ex, sd)], A, A + 365 * 86400, p["cap"], WF[p["wf"]], eq0=100.0, heat=p["heat"], rk_=MP.rk(**p["rk"]))
if __name__ == "__main__":
    P = DX.pool_lv(); E = {}
    EX = {"2.0/1.1": {}, "1.75/1.2": {"soft": 1.75, "take": 1.2}}
    for ex, kw in EX.items():
        Pw = DX.walk(P, **kw)
        for sd in SEEDS: E[(ex, sd)] = MOR.events(Pw, sd)
    with Pool(4, initializer=_init, initargs=(E,)) as Pl:
        res = Pl.map(job, [(ex, nm, sd, A) for ex in EX for nm in VAR for sd in SEEDS for A in X.STARTS + [X.LAST]], chunksize=12)
    R = {}
    for ex, nm, sd, A, r in res: R.setdefault((ex, nm, sd), {})[A] = r
    out = {}
    for ex in EX:
        print(f"выходы ⚡ {ex}", flush=True)
        for nm in VAR:
            b = lambda sd: np.array([R[(ex, "сейчас (v0.99.749)", sd)][A][0] for A in X.STARTS])
            E_ = {sd: np.array([R[(ex, nm, sd)][A][0] for A in X.STARTS]) for sd in SEEDS}
            o = {"p10": np.mean([np.percentile(E_[sd], 10) for sd in SEEDS]), "p50": np.mean([np.median(E_[sd]) for sd in SEEDS]),
                 "p90": np.mean([np.percentile(E_[sd], 90) for sd in SEEDS]),
                 "dd": np.mean([np.median([R[(ex, nm, sd)][A][3] for A in X.STARTS]) for sd in SEEDS]) * 100,
                 "ddmax": np.mean([np.max([R[(ex, nm, sd)][A][3] for A in X.STARTS]) for sd in SEEDS]) * 100,
                 "last12": np.mean([R[(ex, nm, sd)][X.LAST][0] for sd in SEEDS]), "better": np.mean([(E_[sd] > b(sd) * 1.001).sum() for sd in SEEDS]),
                 "liq": int(sum(R[(ex, nm, sd)][A][4] for sd in SEEDS for A in X.STARTS))}
            out[f"{ex} {nm}"] = o
            print(f"   {nm:24s} плохой ${o['p10']:>7,.0f} обычный ${o['p50']:>7,.0f} хороший ${o['p90']:>8,.0f} просадка {o['dd']:.0f}%/{o['ddmax']:.0f}% посл.12 ${o['last12']:>8,.0f} | лучше в {o['better']:.0f}/144 ликв {o['liq']}", flush=True)
    json.dump(out, open(f"{M.ST}/wf/money_recheck.json", "w"), indent=1)
