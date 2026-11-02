"""the strictest money for a module's retrain schedule (roll_mod.py's scores): the module's trades rebuilt by one harness for
every schedule — the judged events over the month's threshold (roll_mod_cmp's rule), one trade a coin & side until its exit, at
most 12 a side, the entry at the level, the stop 1 dATR (the hard one HX x), the exit of the label (SMC: lv_engine's E2 with its
hours; HTF: the traded exit, soft 1 dATR at a 4h close / hard 3 / take 3R / 96 h) — in place of the bot's list in the bundle
(⚡ = the lab's orders, the other modules = the bot's lists), 144 windows x 2 seeds. usage: money_sched.py MOD VAR [VAR...]"""
import sys, os, glob, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import roll_mod as RM, money_arm2 as MA2, money_multi as M, money_expect as X
from numba import njit
from multiprocessing import Pool
F = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125"; SEEDS = (1, 2); ts = RM.ts
MOD, VARS = ARGV[0], ARGV[1:]
@njit
def hold_htf(O, H, L, C, Tb, j, fill, datr):
    risk = fill * datr / 100; ssl = fill - risk; hsl = fill - 3.0 * risk; tp = fill + 3.0 * risk; e = min(len(C), j + 96)
    for q in range(e - j):
        b = j + q
        if L[b] <= hsl or (q > 0 and H[b] >= tp) or ((Tb[b] + 3600) % 14400 == 0 and C[b] <= ssl): return q + 1
    return e - j
def trades(d, SC, INS, names, SYMI, LV, DATR, J, K):
    T, R = d["T"], d["R"]; gname, trm, evm, thm = d["groups"][0]
    thr = np.full(len(T), np.inf); yy, mm = 2023, 1
    while ts(yy, mm) < RM.END:
        a = ts(yy, mm); yy, mm = (yy + 1, 1) if mm == 12 else (yy, mm + 1); b = ts(yy, mm)
        ref = thm & (T >= a - 365 * 86400) & (T < a); x = SC[ref & np.isfinite(SC)]
        if len(x) < 2000: x = np.r_[x, INS[ref & np.isfinite(INS)]]
        if len(x): thr[(T >= a) & (T < b)] = np.quantile(x, d["q"])
    pk = np.flatnonzero(evm & np.isfinite(SC) & (SC >= thr) & (T >= ts(2023)) & (T < RM.END) & np.isfinite(R))
    pk = pk[np.lexsort((-SC[pk], T[pk]))]; busy = {}; act = []; out = []
    for i in pk:
        t = int(T[i]); s = int(d["SIDE"][i]); key = (SYMI[i], s)
        if busy.get(key, 0) > t: continue
        act = [x for x in act if x[0] > t]
        if sum(1 for x in act if x[1] == s) >= 12: continue
        end = t + int(K[i]) * 3600; busy[key] = end; act.append((end, s))
        sym = names[SYMI[i]]; st = max(0.002, float(DATR[i]) / 100)
        out.append({"t0": t, "t1": end, "r": float(R[i]) - 0.03, "st": st, "sth": st * (3.0 if MOD == "htf" else 2.0), "mod": MOD, "sym": sym, "side": s, "e": float(LV[i]), "stream": None})
    return out
_D = {}
def _init(D): _D.update(D)
def job(a):
    v, sd, A = a
    return v, sd, A, MA2.run(_D["or"], _D[v], A, A + 365 * 86400, F, sd)
if __name__ == "__main__":
    d = RM.data(MOD)
    from lv_wf import load_dir
    import lv_engine as LE
    Dd = load_dir("lv2", LE.FNAMES); d["SIDE"] = Dd["SIDE"]; SYMI = Dd["SYM"]; names = Dd["names"]
    LV, J, DT = [], [], []
    for f in sorted(glob.glob("lv2/*.npz")):
        z = np.load(f)
        if len(z["t"]) == 0: continue
        LV.append(z["lv"]); J.append(z["j"]); DT.append(z["datr"])
    LV, J, DATR = np.concatenate(LV), np.concatenate(J).astype(np.int64), np.concatenate(DT)
    if MOD == "smc":
        K = Dd["K"][2]
    else:
        import htf_repro_rl as HR
        K = np.full(len(d["T"]), 96); ev = np.flatnonzero(d["groups"][0][2])
        for k in sorted(set(SYMI[ev])):
            Tb, O, H, L, C, V = HR.load_ls(names[k])
            for i in ev[SYMI[ev] == k]:
                if J[i] < len(C): K[i] = hold_htf(O, H, L, C, Tb, int(J[i]), float(LV[i]), float(DATR[i]))
    base = [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm", MOD}]
    D = {"or": MA2.orders()}
    for v in VARS:
        z = np.load(f"roll_{MOD}_{v}.npz"); tr = trades(d, z["SC"], z["INS"], names, SYMI, LV, DATR, J, K)
        D[v] = sorted(base + tr, key=lambda x: x["t0"])
        print(f"{MOD} {v}: сделок {len(tr)}, {np.mean([x['r'] for x in tr]):+.3f}R (с вычетом 0.03)", flush=True)
    bot = [x for x in M.build("base") if x["mod"] == MOD]
    print(f"{MOD} список бота (для сравнения): сделок {len(bot)}, {np.mean([x['r'] for x in bot]):+.3f}R", flush=True)
    jobs = [(v, sd, A) for v in VARS for sd in SEEDS for A in X.STARTS]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, jobs, chunksize=8)
    R = {}
    for v, sd, A, x in res: R.setdefault(v, {}).setdefault(A, []).append(x)
    b = np.array([np.mean([x[0] for x in R[VARS[0]][A]]) for A in X.STARTS])
    print(f"схема {MOD} | обычный год | плохой год (1 из 10) | просадка медиана | в плохом окне | лучше «{VARS[0]}»", flush=True)
    for v in VARS:
        E = np.array([np.mean([x[0] for x in R[v][A]]) for A in X.STARTS]); dd = np.array([np.mean([x[1] for x in R[v][A]]) for A in X.STARTS])
        print(f"{v} | ${np.median(E):,.0f} | ${np.percentile(E, 10):,.0f} | {np.median(dd) * 100:.0f}% | {np.percentile(dd, 90) * 100:.0f}% | {int((E > b * 1.001).sum())}/{len(b)}", flush=True)
    print("money sched done", MOD, flush=True)
