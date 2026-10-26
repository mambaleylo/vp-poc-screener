"""money: the bundle as deployed vs + an HTF-levels stream from the realistic pipeline lists (htf_x.py / htf_x2.py: the
bot coins, reach filter, touch order, cap 12 a side): SMC exits (close-stop 4h, hard 2 dATR, 96h) or plain (1 dATR touch
stop, take 3R, 72h); per window, the windows from Dec 2024, with / without friction"""
import numpy as np, warnings, json, sys; warnings.filterwarnings("ignore")
exec(open("port_risk2.py").read().split("GRID = [")[0])
use_pool(PC); WB0 = W_abs(-3, 22)
BASE = build2(NEWL)
def rows(fn):
    L = json.load(open(fn)); out = []
    for t in L:
        st_ = max(0.002, abs(t["e"] - t["sl"]) / t["e"]); sth = max(st_, abs(t["e"] - t["hs"]) / t["e"])
        out.append((float(t["t"]), float(t["x"]), float(t["r"]), st_, sth, 1.5, 4, cid(t["s"]), 1.0, 1e18))
    return np.array(out, float)
recent = roll2 >= ts(2024, 12)
def wins(A, rk, fr):
    A = A[np.argsort(A[:, 0], kind="stable")]
    t0, t1, r_, st_, sth, buf, md, ci, wg, tbr = A.T; md = md.astype(np.int64); ci = ci.astype(np.int64)
    if fr: r_ = np.where(md != 0, r_ - 0.03, r_)
    use = np.ones(5, np.bool_); rk_ = np.array(rk, float) / 100
    f = lambda a, b: simx(t0, t1, r_, st_, sth, buf, md, ci, use, rk_, int(np.searchsorted(t0, a)), b, 0.05, wg, 10.0, 20.0, 0.9, 20.0, tbr)
    Y = [f(s_, s_ + 365 * 86400.0) for s_ in roll2]
    return np.array([v[0] for v in Y]), np.array([v[1] for v in Y]), f(ts(2025, 10), ts(2026, 10))[0], f(ts(2026, 1), ts(2026, 10))[0]
L = [(k, "htfS_" + k.replace(" ", "_") + ".json") for k in ("старая q0.993", "новая q0.993", "ИЛИ q0.993", "ИЛИ q0.995", "И q0.98", "И q0.985", "И q0.99", "смесь q0.99", "смесь q0.993")]
for fr in (False, True):
    b, bd, bl, b26 = wins(BASE, [4.5, 3, 2.5, 2, 0], fr)
    print(f"== {'с издержками' if fr else 'как в бэктесте'}: сейчас медиана ${np.median(b):,.0f} 10% ${np.percentile(b, 10):,.0f} просадка {np.median(bd)*100:.0f}% 12 мес ${bl:,.0f} 2026 ${b26:,.0f}", flush=True)
    for nm, fn in L:
        R4 = rows(fn)
        for rk in (1.0, 1.25, 1.5, 2.0):
            y, dd, l, l26 = wins(np.vstack([BASE, R4]), [4.5, 3, 2.5, 2, rk], fr); q = y / b
            print(f"   + HTF {nm:22s} {rk}%: медиана ${np.median(y):>7,.0f} 10% ${np.percentile(y, 10):>6,.0f} просадка {np.median(dd)*100:.0f}% (90%: {np.percentile(dd, 90)*100:.0f}%) | 12 мес ${l:>8,.0f} 2026 ${l26:>7,.0f} | окон лучше {np.mean(q > 1)*100:.0f}% ×{np.median(q):.2f} | с дек.2024 лучше {np.mean(q[recent] > 1)*100:.0f}% ×{np.median(q[recent]):.2f} (худшее ×{q[recent].min():.2f}) | сделок {len(R4)}", flush=True)
