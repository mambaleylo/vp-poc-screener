"""P/R night round: partial takes, caps, entries per hour — on the bot's set (q 0.99, 1h, both BTC filters) and the
check set (q 0.95); R per the hard stop; growth at an equal 1-in-10 drawdown (45% / 50%)"""
import sys, numpy as np
import pr_hyp as P
import prv_wf as W
def cands(q):
    base = P.IDX[(P.SC >= (P.T99 if q == "99" else P.T95))]; base = base[P.TF[base] == 1]
    m = (P.SD * P.F["b_r24"] > -4) & (P.SD * P.F["b_r1"] > -1)
    return base[m[base]]
def run(nm, fn, q, cap=12, per_hour=None):
    z = np.load(f"{W.D}/{fn}.npz"); r = z["cs"].astype(float)
    P.R = np.where(np.abs(r) > 20, np.nan, r); P.KIND = z["kind"]; P.END = P.T + (z["k"].astype(int) + 1) * P.TF * 3600
    tr = P.replay(cands(q), cap=cap, per_hour=per_hour); rr = P.R[tr]; run_ = w = 0
    for j in tr[np.argsort(P.END[tr], kind="stable")]: run_ = run_ + 1 if P.R[j] < 0 else 0; w = max(w, run_)
    yrs = " ".join(f"{rr[(P.T[tr] >= P.ts(y)) & (P.T[tr] < P.ts(y + 1))].mean():+.2f}" for y in (2023, 2024, 2025, 2026))
    target = 0.45 if q == "99" else 0.50
    grid = np.round(np.arange(0.01, 0.20, 0.005), 4) if q == "99" else np.round(np.arange(0.0025, 0.05, 0.0025), 4)
    bs = P.boots(tr, 250); best = None
    for f in grid:
        out = [P.port(tr, f, b) for b in bs]; ds = np.array([a[1] for a in out])
        if np.quantile(ds, .9) <= target: best = (f, np.median([a[0] for a in out]), np.median(ds))
        else: break
    print(f"{nm:34s} q{q} {len(tr):4d} {rr.mean():+.3f} WR {np.mean(rr > 0)*100:3.0f}% минусов {np.mean(rr < 0)*100:3.0f}% подряд {w:2d} | {yrs} | " + (f"{best[0]*100:.1f}%: x{best[1]:,.0f}" if best else "—"), flush=True)
if __name__ == "__main__":
    for q in ("99", "95"):
        print(f"\n=== P/R q{q}")
        run("сейчас (тейк 4.5 ATR)", "prv_lab_cs", q)
        for nm, fn in (("1/3 на +1 ATR → б/у", "px_1_33"), ("1/3 на +1.5 ATR", "px_15_33"), ("1/2 на +1.5 ATR", "px_15_50"),
                       ("1/3 на +2.25 ATR", "px_225_33"), ("1/2 на +2.25 ATR", "px_225_50"), ("1/2 на +3 ATR", "px_3_50")):
            run(nm, fn, q)
        for cap in (4, 6, 8): run(f"не больше {cap} в сторону", "prv_lab_cs", q, cap=cap)
        for ph in (1, 2, 3): run(f"не больше {ph} входа в час в сторону", "prv_lab_cs", q, per_hour=ph)
