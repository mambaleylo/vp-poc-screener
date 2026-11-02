"""P/R's retrain schedules in the strictest money: prv_roll.py's scores -> the trades by prv_lab's replay (the BTC filter, one a
coin & side, 20 a side) as full trades (the entry = the event bar's close, the soft stop 3 ATR, the hard 6 ATR, out after the
label's bars, R - 0.03 as the bundle's lists) in place of the bot's P/R list; 144 windows x 2 seeds. usage: prv_money.py VAR..."""
import os, sys, glob, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "winrate"))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import prv_lab as PL, money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
F = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125"; SEEDS = (1, 2)
z = np.load(f"{PL.ST}/wf/prv_lab_ev.npz"); Xe, T, SY, LAB, BAR = z["X"], z["T"], z["SY"], z["LAB"], z["BAR"]; SD = Xe[:, 1].astype(int)
names = [os.path.basename(f)[:-4] for f in sorted(glob.glob(f"{PL.ST}/prv_ev/*.npz"))]
okb = ~((SD * Xe[:, PL.IB24] <= -4.0) | (SD * Xe[:, PL.IB1] <= -1.0))
def lst(VAR):
    s = np.load(f"{PL.ST}/wf/prv_roll_{VAR}_sc.npz"); SC, THR = s["SC"], s["THR"]
    sel = np.flatnonzero(np.isfinite(SC) & (SC >= THR) & okb); o = sel[np.argsort(T[sel], kind="stable")]
    R, B = LAB[:, 0], BAR[:, 0]; busy, act, out = {}, [], []; cache = {}
    for j in o:
        if not R[j] == R[j] and B[j] <= 0: continue
        t = int(T[j]); key = (SY[j], SD[j])
        if busy.get(key, 0) > t: continue
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == SD[j]) >= 20: continue
        end = t + max(int(B[j]), 1) * 3600; busy[key] = end
        if not R[j] == R[j]: continue
        act.append((end, SD[j])); sym = names[SY[j]]
        if sym not in cache:
            Tb, O, H, L, C = PL.load1h(sym); cache[sym] = (Tb, C, PL.wilder(H, L, C, 14))
        Tb, C, A = cache[sym]; i = int(np.searchsorted(Tb, t - 3600)); e = float(C[i]); a = float(A[i])
        out.append({"t0": t, "t1": end, "r": float(R[j]) - 0.03, "st": 3 * a / e, "sth": 6 * a / e, "mod": "prv", "sym": sym, "side": int(SD[j]), "e": e, "stream": None})
    return out
_D = {}
def _init(D): _D.update(D)
def job(a):
    v, sd, A = a
    return v, sd, A, MA2.run(_D["or"], _D[v], A, A + 365 * 86400, F, sd)
if __name__ == "__main__":
    VARS = ARGV; base = [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm", "prv"}]
    bot = [v for v in M.build("base") if v["mod"] == "prv"]
    D = {"or": MA2.orders(), "список бота": sorted(base + bot, key=lambda x: x["t0"])}
    print(f"список бота: {len(bot)} сделок {np.mean([x['r'] for x in bot]):+.3f}R", flush=True)
    for v in VARS:
        tr = lst(v); D[v] = sorted(base + tr, key=lambda x: x["t0"]); print(f"{v}: {len(tr)} сделок {np.mean([x['r'] for x in tr]):+.3f}R", flush=True)
    K = ["список бота"] + VARS
    jobs = [(v, sd, A) for v in K for sd in SEEDS for A in X.STARTS]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, jobs, chunksize=8)
    R = {}
    for v, sd, A, x in res: R.setdefault(v, {}).setdefault(A, []).append(x)
    b = np.array([np.mean([x[0] for x in R[VARS[0]][A]]) for A in X.STARTS])
    print(f"схема P/R | обычный год | плохой год (1 из 10) | просадка медиана | в плохом окне | лучше «{VARS[0]}»", flush=True)
    for v in K:
        E = np.array([np.mean([x[0] for x in R[v][A]]) for A in X.STARTS]); dd = np.array([np.mean([x[1] for x in R[v][A]]) for A in X.STARTS])
        print(f"{v} | ${np.median(E):,.0f} | ${np.percentile(E, 10):,.0f} | {np.median(dd) * 100:.0f}% | {np.percentile(dd, 90) * 100:.0f}% | {int((E > b * 1.001).sum())}/{len(b)}", flush=True)
    print("prv money done", flush=True)
