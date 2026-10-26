"""money: the bundle as deployed (v0.99.727: risks ⚡4.5 / P/R3 / SMC2.5 / EMA2, cross 10x, open risk <= 90%, SMC
break-even) vs + an inversion-FVG stream (lv7 fam ifvg_l / ifvg_s on 4h + 1d, exit E2: stop 1 dATR, take 3R, 72h;
the yearly walk-forward model, q of the previous year's out-of-sample scores, cap 12 a side, every coin) at risks 1-3%;
one position per coin across the modules (simx's rule); with and without -0.03R friction on the non-⚡ rows"""
import numpy as np, warnings, os, sys; warnings.filterwarnings("ignore")
DR, ENG, MASK, NMX, RK4 = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], float(sys.argv[5])
exec(open("port_risk2.py").read().split("GRID = [")[0])
from lv_wf import load_dir, scores, select
import importlib
LX = importlib.import_module(ENG)
Dd = load_dir(DR, LX.FNAMES); Fv = Dd["F"]; fam = Fv[:, 0].astype(int); Tv = Dd["T"]; e = 2
gm = eval(MASK)
SCF = f"{NMX}_sc.npz"
if os.path.exists(SCF):
    z = np.load(SCF, allow_pickle=True); SC = z["SC"]; THR = z["THR"].item()
else:
    SC, THR = scores(Dd, e, mask=gm, seeds=2); np.savez(SCF, SC=SC, THR=np.array(THR, dtype=object))
use_pool(PC); WB0 = W_abs(-3, 22)
BASE = build2(NEWL)
def rows_new(q):
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

def wins(A, rk, fr):
    A = A[np.argsort(A[:, 0], kind="stable")]
    t0, t1, r_, st_, sth, buf, md, ci, wg, tbr = A.T; md = md.astype(np.int64); ci = ci.astype(np.int64)
    if fr: r_ = np.where(md != 0, r_ - 0.03, r_)
    use = np.ones(5, np.bool_); rk_ = np.array(rk, float) / 100
    f = lambda a, b: simx(t0, t1, r_, st_, sth, buf, md, ci, use, rk_, int(np.searchsorted(t0, a)), b, 0.05, wg, 10.0, 20.0, 0.9, 20.0, tbr)
    return np.array([f(s_, s_ + 365 * 86400.0)[0] for s_ in roll2])
IF = rows_new(0.995)
for fr in (False, True):
    b = wins(BASE, (4.5, 3, 2.5, 2, 0), fr); y = wins(np.vstack([BASE, IF]), (4.5, 3, 2.5, 2, RK4), fr)
    print(f"== {NMX} {RK4}% {'с издержками' if fr else 'как в бэктесте'}: окна по началу (каждое 4-е), сейчас -> с добавкой", flush=True)
    for k in range(0, len(roll2), 4):
        print(f"   {str(np.datetime64(int(roll2[k]), 's'))[:10]}: ${b[k]:>9,.0f} -> ${y[k]:>9,.0f}  ×{y[k] / b[k]:.2f}", flush=True)
    q = np.argsort(b); top = q[-len(q) // 4:]; low = q[:len(q) // 4]
    print(f"   лучшая четверть окон (как сейчас): медиана отношения ×{np.median(y[top] / b[top]):.2f}; худшая четверть: ×{np.median(y[low] / b[low]):.2f}", flush=True)
