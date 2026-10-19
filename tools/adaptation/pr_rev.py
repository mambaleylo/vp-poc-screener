"""1h only: the BTC filter grid again (24 h x 1 h thresholds) and the exits (stop by close vs on touch), at an equal
1-in-10 drawdown. q 99 = the bot, q 95 = the check set."""
import sys, numpy as np
ARGS = sys.argv[1:]
import pr_hyp as P
import prv_wf as W
q = ARGS[0]; mode = ARGS[1] if len(ARGS) > 1 else "grid"
base = P.IDX[(P.SC >= (P.T99 if q == "99" else P.T95))]
base = base[P.TF[base] == 1]
F, SD = P.F, P.SD
target = 0.45 if q == "99" else 0.50
grid = ([0.01, 0.015, 0.02, 0.025, 0.03, 0.035, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.12, 0.14] if q == "99"
        else [0.0025, 0.005, 0.0075, 0.01, 0.0125, 0.015, 0.02, 0.025, 0.03])
CS = P.R.copy()
lab3 = np.load(f"{W.D}/prv_lab3.npz")
TOUCH30 = lab3["s30_t45"].astype(float); TOUCH30 = np.where(np.abs(TOUCH30) > 20, np.nan, TOUCH30)
OLD = W.lab_of(1.5, 3.0)
def eq_pain(tr, nb=250):
    bs = P.boots(tr, nb); best = None
    for f in grid:
        rr = [P.port(tr, f, b) for b in bs]; ds = np.array([a[1] for a in rr])
        if np.quantile(ds, .9) <= target: best = (f, np.median([a[0] for a in rr]), np.median(ds))
        else: break
    return best
def line(nm, tr):
    r = P.R[tr]; run = w = 0
    for j in tr[np.argsort(P.END[tr], kind="stable")]: run = run + 1 if P.R[j] < 0 else 0; w = max(w, run)
    yrs = " ".join(f"{r[(P.T[tr] >= P.ts(y)) & (P.T[tr] < P.ts(y + 1))].mean():+.2f}" for y in (2023, 2024, 2025, 2026))
    b = eq_pain(tr)
    print(f"{nm:28s} {len(tr):5d} {r.mean():+.3f} {np.mean(r > 0)*100:3.0f}% минусов подряд {w:2d} | {yrs} | " + (f"{b[0]*100:5.2f}%: x{b[1]:8.1f} (обычная {b[2]*100:.0f}%)" if b else "—"), flush=True)
if mode == "grid":
    print(f"== q {q}, только 1ч, стоп по закрытию: BTC 24ч порог x BTC 1ч порог | при просадке 1 из 10 = {target:.0%}: риск, рост")
    for l24 in (None, 3, 4, 5, 6):
        for l1 in (None, 0.5, 1.0, 1.5, 2.0):
            m = np.ones(len(SD), bool)
            if l24: m &= SD * F["b_r24"] > -l24
            if l1: m &= SD * F["b_r1"] > -l1
            line(f"24ч {l24 or '—'} / 1ч {l1 or '—'}", P.replay(base[m[base]]))
else:
    l24, l1 = float(ARGS[2]), float(ARGS[3])
    m = (SD * F["b_r24"] > -l24) & (SD * F["b_r1"] > -l1)
    print(f"== q {q}, только 1ч, фильтр 24ч {l24} / 1ч {l1}: выходы")
    for nm, lab in (("стоп по закрытию 3 / авар. 6", CS), ("стоп 3 ATR касанием", TOUCH30), ("старое: стоп 1.5, тейк 3R", OLD)):
        P.R = lab
        line(nm, P.replay(base[m[base]]))
    P.R = CS
