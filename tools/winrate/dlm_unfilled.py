"""⚡'s never-filled limits (the user: "изучи поведение не исполненных лимиток, может если точку входа поменять и они были бы
так же эффективны? для не исполненных нужен другой atr для входа?"): every order over its stream's threshold 2023-2026
(money_arm2.orders: 62k, ~14% filled). (1) how near the price came to the unfilled ones within their 4 bars (ATR); (2) every
limit nearer the price by d ATR — the fills, the R of the old fills (a worse entry) and of the new ones; (3) the chase: a
limit not filled in its first k bars moved d ATR nearer for the rest of its life; (4) the money of the best ones (the
strictest money, the bot's settings: the coin's maximum leverage, 144 windows x 2 seeds)."""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X, dlm_engine as DE
from multiprocessing import Pool
F = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125"; SEEDS = (1, 2)
TAKE, SOFT, HARD = 1.2, 1.75, 3.0


def walk(xs, lvs, t0s, alive):
    """fill_walk of the orders xs (one coin & stream) at the levels lvs from t0s for `alive` bars"""
    c, st = xs[0]["coin"], xs[0]["stream"]
    if c not in MA2.H1: MA2.H1[c] = DE.load1h(c)
    T1, O1, Hh, Ll, C1, V1 = MA2.H1[c]; p = DE.STREAMS[st]; bs = p["hh"] * 3600
    return DE.fill_walk(T1, O1, Hh, Ll, C1, np.array(t0s, np.int64), np.array([x["side"] for x in xs], np.int64), np.array(lvs, float),
                        np.array([x["atr"] for x in xs]), bs, p["ch"], alive, DE.HOLD, TAKE, SOFT, HARD, DE.FEE_IN, DE.FEE_TAKE, DE.FEE_OUT, DE.FUND)


def variant(OR, d, k=0):
    """every order d ATR nearer the price (k = 0) or moved so after k bars unfilled (the chase)"""
    out = []; by = {}
    for o in OR: by.setdefault((o["coin"], o["stream"]), []).append(o)
    for (c, st), xs in by.items():
        bs = DE.STREAMS[st]["hh"] * 3600
        lv2 = [x["lv"] + x["side"] * d * x["atr"] for x in xs]
        if k == 0:
            fl, t1h, fill, R, kind, tout = walk(xs, lv2, [x["t"] for x in xs], DE.ALIVE)
            res = [(fl[i], t1h[i], fill[i], R[i], tout[i], lv2[i]) for i in range(len(xs))]
        else:
            a = walk(xs, [x["lv"] for x in xs], [x["t"] for x in xs], k)
            b = walk(xs, lv2, [x["t"] + k * bs for x in xs], DE.ALIVE - k)
            res = [(a[0][i], a[1][i], a[2][i], a[3][i], a[5][i], xs[i]["lv"]) if a[0][i] else (b[0][i], b[1][i], b[2][i], b[3][i], b[5][i], lv2[i]) for i in range(len(xs))]
        for x, (f, t1h_, e_, R_, to_, lv_) in zip(xs, res):
            f = bool(f); e = float(e_) if f else lv_
            out.append(dict(x, lv=float(lv_), filled=f, t1h=int(t1h_), e=e, r=float(R_), t1=int(to_), st=SOFT * x["atr"] / e, sth=HARD * x["atr"] / e, was=x["filled"]))
    out.sort(key=lambda o: o["t"]); return out


def gaps(OR):
    """the unfilled ones: how near (ATR) the price came within their life"""
    g = []
    for o in OR:
        if o["filled"]: continue
        c = o["coin"]
        if c not in MA2.H1: MA2.H1[c] = DE.load1h(c)
        T1, O1, Hh, Ll, C1, V1 = MA2.H1[c]
        i0, i1 = np.searchsorted(T1, o["t"]), np.searchsorted(T1, o["until"])
        if i1 <= i0: continue
        g.append(((Ll[i0:i1].min() - o["lv"]) if o["side"] > 0 else (o["lv"] - Hh[i0:i1].max())) / o["atr"])
    return np.array(g)


VARS = {"сейчас": (0, 0), "все ближе на 0.1 ATR": (0.1, 0), "все ближе на 0.2 ATR": (0.2, 0), "все ближе на 0.3 ATR": (0.3, 0), "все ближе на 0.5 ATR": (0.5, 0),
        "догон: после 1 свечи ближе на 0.2": (0.2, 1), "догон: после 1 свечи ближе на 0.3": (0.3, 1), "догон: после 2 свечей ближе на 0.3": (0.3, 2),
        "догон: после 2 свечей ближе на 0.5": (0.5, 2)}
_D = {}
def _init(D): _D.update(D)
def job(a):
    v, sd, A = a
    return v, sd, A, MA2.run(_D[v], _D["ot"], A, A + 365 * 86400, F, sd)


if __name__ == "__main__":
    OR = MA2.orders()
    g = gaps(OR)
    n = len(OR); nf = sum(o["filled"] for o in OR)
    print(f"лимиток {n}, исполнились {nf} ({nf / n * 100:.0f}%); не исполнились {len(g)}: цена не дошла "
          + ", ".join(f"≤{x} ATR — {np.mean(g <= x) * 100:.0f}%" for x in (0.05, 0.1, 0.2, 0.3, 0.5, 1.0)) + f", медиана {np.median(g):.2f} ATR", flush=True)
    D = {"ot": [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]}
    for v, (d, k) in VARS.items():
        D[v] = variant(OR, d, k)   # d = 0: the same walk as the others (checked against the stored orders below)
        fl = [o for o in D[v] if o["filled"] and np.isfinite(o["r"])]
        old = [o["r"] for o in fl if o.get("was", True)]; new = [o["r"] for o in fl if not o.get("was", True)]
        print(f"{v}: исполнились {len(fl)} ({len(fl) / n * 100:.0f}%), R всех {np.mean([o['r'] for o in fl]):+.3f}; прежние {len(old)} {np.mean(old):+.3f}R"
              + (f"; новые {len(new)} {np.mean(new):+.3f}R" if new else ""), flush=True)
    z0 = D["сейчас"]; same = np.mean([(a_["filled"] == b_["filled"]) and (not a_["filled"] or abs(a_["r"] - b_["r"]) < 1e-3) for a_, b_ in zip(z0, OR)])
    print(f"проверка: перепроход без сдвига совпал с сохранёнными лимитками в {same * 100:.2f}%", flush=True)
    jobs = [(v, sd, A) for v in VARS for sd in SEEDS for A in X.STARTS]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, jobs, chunksize=8)
    R = {}
    for v, sd, A, x in res: R.setdefault(v, {}).setdefault(A, []).append(x)
    b = np.array([np.mean([x[0] for x in R["сейчас"][A]]) for A in X.STARTS])
    print("вариант | обычный год | плохой год | просадка медиана | в плохом окне | лучше нынешнего", flush=True)
    for v in VARS:
        E = np.array([np.mean([x[0] for x in R[v][A]]) for A in X.STARTS]); dd = np.array([np.mean([x[1] for x in R[v][A]]) for A in X.STARTS])
        print(f"{v} | ${np.median(E):,.0f} | ${np.percentile(E, 10):,.0f} | {np.median(dd) * 100:.0f}% | {np.percentile(dd, 90) * 100:.0f}% | {int((E > b * 1.001).sum())}/{len(b)}", flush=True)
    print("unfilled done", flush=True)
