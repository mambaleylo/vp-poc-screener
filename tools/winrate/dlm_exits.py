"""⚡ exits on the walk-forward pool: the bot's pool (dlm_pool's rules on the walk-forward scores, the bot's coins) re-walked
on the 1h candles with other exits — the take (1.1 ATR), the time exit (32 bars), the close stop (2 ATR), the emergency
stop (3 ATR), the limit's life (4 bars: a shorter life = the trades that filled sooner) — one at a time; the trades' R
and the bundle's money (money_expect.py's: a year from $100, 144 weekly windows, 14x, the 2h shorts x0.5, WaveTrend,
EMA 3%, the cap 95%). The pool's slots kept (a coin busy as with the bot's exits). -> <LABSTORE>/wf/dlm_exits.json"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlm_engine as DE, dlm_pool as DP, money_multi as M, money_expect as X, money_osc as O, money_params as MP
from multiprocessing import Pool
def pool_lv():
    P = DP.pool(["train", "check", "base"]); key = {}
    for st in ("wick4h", "close2h"):
        z = np.load(f"{DP.ST}/wf/scores_{st}.npz", allow_pickle=True)
        for c, t, s, lv in zip(z["coin"], z["t"], z["side"], z["lv"]): key[(st, str(c), int(t), int(s))] = float(lv)
    for x in P: x["lv"] = key[(x["st"], x["coin"], x["t0"], x["side"])]
    return P
H1 = {}
def walk(P, take=DE.TAKE, hold=DE.HOLD, soft=DE.SOFT, hard=DE.HARD, alive=DE.ALIVE):
    out = []
    by = {}
    for x in P: by.setdefault(x["coin"], []).append(x)
    for c, xs in by.items():
        if c not in H1: H1[c] = DE.load1h(c)
        T1, O1, H1_, L1, C1, V1 = H1[c]
        for st in ("wick4h", "close2h"):
            ys = [x for x in xs if x["st"] == st]
            if not ys: continue
            p = DE.STREAMS[st]; bs = p["hh"] * 3600
            fl, t1h, fill, R, kind, tout = DE.fill_walk(T1, O1, H1_, L1, C1, np.array([y["t0"] for y in ys], np.int64), np.array([y["side"] for y in ys], np.int64),
                                                        np.array([y["lv"] for y in ys]), np.array([y["atr"] for y in ys]), bs, p["ch"], alive, hold, take, soft, hard,
                                                        DE.FEE_IN, DE.FEE_TAKE, DE.FEE_OUT, DE.FUND)
            for k, y in enumerate(ys):
                if fl[k]: out.append(dict(y, t1h=int(t1h[k]), fill=float(fill[k]), R=float(R[k]), kind=int(kind[k]), tout=int(tout[k]),
                                          sl=float(fill[k]) - y["side"] * soft * y["atr"], hsl=float(fill[k]) - y["side"] * hard * y["atr"]))
    return out
def events(Pw):
    EV = []   # ⚡ first within an hour, as money_multi.build (the bot's ⚡ limits are armed — in the open risk — before they fill)
    for x in sorted(Pw, key=lambda x: (x["t1h"], -x["score"])):   # the pool's order: the touch hour, then the score
        EV.append({"t0": x["t1h"] + 3600, "t1": x["tout"], "r": x["R"], "st": abs(x["fill"] - x["sl"]) / x["fill"], "sth": abs(x["fill"] - x["hsl"]) / x["fill"],
                   "mod": "dlm", "sym": M.bn(x["coin"]), "side": x["side"], "e": x["fill"], "stream": x["st"]})
    EV += [v for v in M.build("base") if v["mod"] != "dlm"]
    EV.sort(key=lambda v: v["t0"]); return EV
VAR = {"сейчас": {}, "тейк 0.8": {"take": 0.8}, "тейк 1.0": {"take": 1.0}, "тейк 1.3": {"take": 1.3}, "тейк 1.5": {"take": 1.5}, "тейк 2.0": {"take": 2.0},
       "время 16": {"hold": 16}, "время 24": {"hold": 24}, "время 48": {"hold": 48}, "время 64": {"hold": 64},
       "стоп 1.5": {"soft": 1.5}, "стоп 2.5": {"soft": 2.5}, "авар. 2.5": {"hard": 2.5}, "авар. 4": {"hard": 4.0},
       "лимитка 2 свечи": {"alive": 2}, "лимитка 3 свечи": {"alive": 3}}
_E = {}
def job(a):
    nm, A = a
    return nm, A, M.run(_E[nm], A, A + 365 * 86400, 14.0, O.W_OSC, eq0=100.0, heat=0.95, rk_=MP.rk(emx=3.0))
def _init(E):
    _E.update(E)
if __name__ == "__main__":
    P = pool_lv(); E = {}; S = {}
    for nm, kw in VAR.items():
        Pw = walk(P, **kw); E[nm] = events(Pw)
        r = np.array([x["R"] for x in Pw]); yr = np.array([int(np.datetime64(x["t1h"], "s").astype("datetime64[Y]").astype(int) + 1970) for x in Pw])
        S[nm] = {"n": len(r), "R": float(r.mean()), "wr": float((r > 0).mean()), "years": {int(y): round(float(r[yr == y].mean()), 3) for y in np.unique(yr)}}
        print(f"{nm:16s} сделок {len(r)} средний R {r.mean():+.3f} WR {(r > 0).mean()*100:.0f}% | по годам " + " ".join(f"{y}:{v:+.2f}" for y, v in S[nm]["years"].items()), flush=True)
    with Pool(4, initializer=_init, initargs=(E,)) as Pl:
        res = Pl.map(job, [(nm, A) for nm in VAR for A in X.STARTS + [X.LAST]], chunksize=6)
    R = {}
    for nm, A, r in res: R.setdefault(nm, {})[A] = r
    b0 = np.array([R["сейчас"][A][0] for A in X.STARTS])
    for nm, v in R.items():
        Ea = np.array([v[A][0] for A in X.STARTS]); dd = np.array([v[A][3] for A in X.STARTS])
        S[nm].update(p10=int(np.percentile(Ea, 10)), p50=int(np.median(Ea)), dd=int(round(np.median(dd) * 100)), ddmax=int(round(dd.max() * 100)),
                     last12=int(v[X.LAST][0]), better=int((Ea > b0 * 1.001).sum()), q50=float(np.median(Ea / b0)))
        s = S[nm]
        print(f"{nm:16s} плохой ${s['p10']:>6,} обычный ${s['p50']:>7,} просадка {s['dd']}%/{s['ddmax']}% посл.12 ${s['last12']:>8,} | лучше в {s['better']:3d}/144 x{s['q50']:.2f}", flush=True)
    json.dump(S, open(f"{M.ST}/wf/dlm_exits.json", "w"), indent=1)
