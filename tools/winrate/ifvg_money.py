"""money: the bundle as deployed (v0.99.727: risks ⚡4.5 / P/R3 / SMC2.5 / EMA2, cross 10x, open risk <= 90%, SMC
break-even) vs + an inversion-FVG stream (lv7 fam ifvg_l / ifvg_s on 4h + 1d, exit E2: stop 1 dATR, take 3R, 72h;
the yearly walk-forward model, q of the previous year's out-of-sample scores, cap 12 a side, every coin) at risks 1-3%;
one position per coin across the modules (simx's rule); with and without -0.03R friction on the non-⚡ rows"""
import numpy as np, warnings, os; warnings.filterwarnings("ignore")
exec(open("port_risk2.py").read().split("GRID = [")[0])
from lv_wf import load_dir, scores, select
import lv7_engine as L7
Dd = load_dir("lv7", L7.FNAMES); Fv = Dd["F"]; fam = Fv[:, 0].astype(int); Tv = Dd["T"]; e = 2
gm = (fam % 6 == 2) | (fam % 6 == 3)
if os.path.exists("ifvg_sc.npz"):
    z = np.load("ifvg_sc.npz", allow_pickle=True); SC = z["SC"]; THR = z["THR"].item()
else:
    SC, THR = scores(Dd, e, mask=gm, seeds=2); np.savez("ifvg_sc.npz", SC=SC, THR=np.array(THR, dtype=object))
use_pool(PC); WB0 = W_abs(-3, 22)
BASE = build2(NEWL)
def rows_ifvg(q):
    s = select(Dd, e, SC, THR, q, 12, gm); s = s[Tv[s] >= ts(2022)]
    out = []
    for i in s:
        stp = float(Fv[i, 3]) / 100 * 1.0
        out.append((float(Tv[i]), float(Tv[i] + Dd["K"][e][i] * 3600), float(Dd["R"][e][i]), stp, stp, 1.5, 4, cid(Dd["names"][Dd["SYM"][i]]), 1.0, 1e18))
    return np.array(out, float)
def ys(A, rk, fr):
    A = A[np.argsort(A[:, 0], kind="stable")]
    t0, t1, r_, st_, sth, buf, md, ci, wg, tbr = A.T; md = md.astype(np.int64); ci = ci.astype(np.int64)
    if fr: r_ = np.where(md != 0, r_ - 0.03, r_)
    use = np.ones(5, np.bool_); rk_ = np.array(rk, float) / 100
    f = lambda a, b: simx(t0, t1, r_, st_, sth, buf, md, ci, use, rk_, int(np.searchsorted(t0, a)), b, 0.05, wg, 10.0, 20.0, 0.9, 20.0, tbr)
    Y = [f(s_, s_ + 365 * 86400.0) for s_ in roll2]
    l = f(ts(2025, 10), ts(2026, 10)); l26 = f(ts(2026, 1), ts(2026, 10))
    return np.array([v[0] for v in Y]), np.array([v[1] for v in Y]), l[0], l26[0], l[2]
for q in (0.995, 0.99):
    IF = rows_ifvg(q)
    yrs = np.array([int(np.datetime64(int(t), "s").astype("datetime64[Y]").astype(int) + 1970) for t in IF[:, 0]])
    print(f"== iFVG q{q}: сделок {len(IF)} ср.R {IF[:, 2].mean():+.3f} WR {(IF[:, 2] > 0).mean()*100:.0f}% стоп медиана {np.median(IF[:, 3])*100:.1f}% | " +
          " ".join(f"{Y % 100}:{IF[yrs == Y, 2].mean():+.2f}({(yrs == Y).sum()})" for Y in range(2022, 2027)), flush=True)
    for fr in (False, True):
        b, bd, bl, b26, _ = ys(BASE, (4.5, 3, 2.5, 2, 0), fr)
        print(f"  {'с издержками' if fr else 'как в бэктесте'}: сейчас медиана ${np.median(b):,.0f} 10% ${np.percentile(b, 10):,.0f} просадка {np.median(bd)*100:.0f}% (90%: {np.percentile(bd, 90)*100:.0f}%) 12 мес ${bl:,.0f} 2026 ${b26:,.0f}", flush=True)
        for rk4 in (1.0, 1.5, 2.0, 2.5, 3.0):
            y, dd, l, l26, nm_ = ys(np.vstack([BASE, IF]), (4.5, 3, 2.5, 2, rk4), fr)
            print(f"    + iFVG {rk4}%: медиана ${np.median(y):>7,.0f} 10% ${np.percentile(y, 10):>6,.0f} просадка {np.median(dd)*100:.0f}% (90%: {np.percentile(dd, 90)*100:.0f}%) | 12 мес ${l:>8,.0f} 2026 ${l26:>7,.0f} | окон лучше {np.mean(y > b)*100:.0f}% · ×{np.median(y / b):.2f} · сделок iFVG за 12 мес {int(nm_[4])}", flush=True)
