"""P/R round 2: the combos of prv_lab.py's best (the market entry, the take 6 ATR, the BTC filter off / 6% & 1.5%) by year,
and the money: P/R's trades of each variant (this pipeline's walk-forward) in place of the list's in the bundle (the
strictest money, the bot's settings, 144 windows x 2 seeds) -> the tables"""
import os, sys, json, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import prv_lab as PL
PL.VAR = {"сейчас": (0.3, 3, 3.0, 6.0, 4.5, 48, 0.0), "рынок": (0.0, 1, 3.0, 6.0, 4.5, 48, 0.0), "тейк 6": (0.3, 3, 3.0, 6.0, 6.0, 48, 0.0),
          "рынок + тейк 6": (0.0, 1, 3.0, 6.0, 6.0, 48, 0.0)}
COMBO = {"сейчас": ("сейчас", (4.0, 1.0)), "вход по рынку": ("рынок", (4.0, 1.0)), "тейк 6 ATR": ("тейк 6", (4.0, 1.0)),
         "без фильтра BTC": ("сейчас", (99, 99)), "рынок + тейк 6": ("рынок + тейк 6", (4.0, 1.0)),
         "рынок + тейк 6 + без фильтра BTC": ("рынок + тейк 6", (99, 99)), "рынок + тейк 6 + BTC 6% / 1.5%": ("рынок + тейк 6", (6.0, 1.5))}
_D = {}


def job(a):
    v, sd, A = a
    pr = _D["list"] if v.startswith("P/R как") else [x for x in _D[f"L{v}"] if x["sym"]]
    return v, sd, A, _D["MA2"].run(_D["or"], sorted(_D["ot0"] + pr, key=lambda x: x["t0"]), A, A + 365 * 86400, _D["F"], sd)


if __name__ == "__main__":
    import glob
    ST = PL.ST
    files = sorted(glob.glob(f"{ST}/prv_ev/*.npz")); SYMS = [os.path.basename(f)[:-4] for f in files]
    fn = f"{ST}/wf/prv_lab2_ev.npz"
    if os.path.exists(fn):
        z = np.load(fn); X, T, SY, LAB, BAR = z["X"], z["T"], z["SY"], z["LAB"], z["BAR"]
    else:
        X, T, SY, LAB, BAR = PL.build(); np.savez(fn, X=X, T=T, SY=SY, LAB=LAB, BAR=BAR)
    z = np.load(f"{ST}/wf/prv_lab.npz"); SC = z["SC"]; assert len(SC) == len(T)
    SD = X[:, 1].astype(int); ATRP = X[:, PL.NAMES.index("atrp")]
    # the thresholds as prv_lab: the quarter's model's 99% of its last 12 months -> recomputed from the stored scores is not
    # possible (the in-window scores were not stored), so the threshold is the 99% quantile of the scores of the 12 months
    # before each quarter (out-of-sample scores, available from 2024-01; 2023 uses its own quarter's 99%)
    QT = [(y, m) for y in range(2023, 2027) for m in (1, 4, 7, 10) if (y, m) <= (2026, 7)]
    thr = np.full(len(T), np.inf)
    for (y, m) in QT:
        a0 = PL.ts(y, m); a1 = PL.ts(y + (m + 3 > 12), (m + 3 - 1) % 12 + 1); te = (T >= a0) & (T < a1)
        for s in (1, -1):
            ref = (T >= max(a0 - 365 * 86400, PL.ts(2023))) & (T < a0) & (SD == s) & np.isfinite(SC)
            if ref.sum() < 1000: ref = te & (SD == s) & np.isfinite(SC)
            thr[te & (SD == s)] = np.nanquantile(SC[ref], 0.99)
    YRS = (2023, 2024, 2025, 2026); WK = {2023: 52, 2024: 52, 2025: 52, 2026: 39}
    lists = {}
    print("вариант | 2023 | 2024 | 2025 | 2026 | итого", flush=True)
    for nm, (v, bf) in COMBO.items():
        vi = list(PL.VAR).index(v)
        okb = ~((SD * X[:, PL.IB24] <= -bf[0]) | (SD * X[:, PL.IB1] <= -bf[1]))
        sel = np.flatnonzero(np.isfinite(SC) & (SC >= thr) & okb)
        out = PL.replay(sel, T, SY, SD, LAB[:, vi], BAR[:, vi])
        # the trades for the money: the entry ~ the event's close, the size by the hard stop (6 ATR)
        idx = {(int(T[j]), int(SY[j]), int(SD[j])): j for j in sel}
        tr = []
        for t, r in out:
            pass
        sel_sorted = sel[np.argsort(T[sel], kind="stable")]
        busy, act = {}, []
        for j in sel_sorted:
            R, B = LAB[j, vi], BAR[j, vi]
            if not R == R and B <= 0: continue
            key = (SY[j], SD[j]); t = int(T[j])
            if busy.get(key, 0) > t: continue
            act = [a for a in act if a[0] > t]
            if sum(1 for a in act if a[1] == SD[j]) >= 20: continue
            end = t + max(int(B), 1) * 3600; busy[key] = end
            if R == R:
                act.append((end, SD[j])); st = 6.0 * float(ATRP[j]) / 100
                tr.append({"t0": t, "t1": end, "r": float(R) - 0.03, "st": st, "sth": st, "mod": "prv", "sym": SYMS[SY[j]], "side": int(SD[j]), "e": 1.0, "stream": None})
        lists[nm] = tr
        cells = []
        for Y in YRS:
            r = [x["r"] + 0.03 for x in tr if int(1970 + (x["t0"] / 86400 + 0.5) / 365.2425) == Y]
            cells.append(f"{np.mean(r):+.2f}R {len(r) / WK[Y]:.1f}/нед" if r else "—")
        print(f"{nm} | " + " | ".join(cells) + f" | {np.mean([x['r'] + 0.03 for x in tr]):+.3f}R, {len(tr)} сделок", flush=True)
    json.dump(lists, open(f"{ST}/wf/prv_lab2_lists.json", "w"))
    # the money
    sys.path.insert(0, os.path.join(HERE, "..", "winrate"))
    ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
    import money_arm2 as MA2, money_multi as M, money_expect as X_
    from multiprocessing import Pool
    F = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125"
    for nm in lists:   # the entry price (the unrealized P&L): the last close by the entry hour
        for x in lists[nm]: x["e"] = M.px_at(x["sym"], x["t0"] + 3600) or 0.0
        lists[nm] = [x for x in lists[nm] if x["e"] > 0]
    OR = MA2.orders(); OT0 = [v for v in M.build("base") if v["mod"] in X_.KINDS["bundle_htf"] - {"dlm", "prv"}]
    D = {"or": OR, "ot0": OT0, **{f"L{nm}": lists[nm] for nm in COMBO}, "list": [v for v in M.build("base") if v["mod"] == "prv"]}
    VARS = ["P/R как в боте (список бэктеста)"] + list(COMBO)
    _D.update(D, F=F, MA2=MA2)
    with Pool(4) as Pl:
        res = Pl.map(job, [(v, sd, A) for v in VARS for sd in (1, 2) for A in X_.STARTS], chunksize=8)
    R = {}
    for v, sd, A, x in res: R.setdefault(v, {}).setdefault(A, []).append(x)
    b = np.array([np.mean([x[0] for x in R["сейчас"][A]]) for A in X_.STARTS])
    print("деньги — P/R в связке | обычный год | плохой год | просадка медиана | в плохом окне | лучше «сейчас» (та же схема)", flush=True)
    for v in VARS:
        E = np.array([np.mean([x[0] for x in R[v][A]]) for A in X_.STARTS]); dd = np.array([np.mean([x[1] for x in R[v][A]]) for A in X_.STARTS])
        print(f"{v} | ${np.median(E):,.0f} | ${np.percentile(E, 10):,.0f} | {np.median(dd) * 100:.0f}% | {np.percentile(dd, 90) * 100:.0f}% | {int((E > b * 1.001).sum())}/{len(b)}", flush=True)
    print("prv lab2 done", flush=True)
