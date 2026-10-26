"""money: the bundle as deployed vs + the diversifier candidates (HTF levels lv2 fam <= 22, volume profile lv5 fam <= 5,
classic ev3), each its own walk-forward model (cached from div_screen.py), E2 (stop 1 dATR, take 3R, 72h), q 0.995,
cap 12 a side, every coin; one position per coin across the modules; with and without -0.03R friction on the non-⚡ rows;
the share of windows better overall and among the windows starting from Dec 2024 (the recent regime)"""
import numpy as np, warnings, os, sys, importlib; warnings.filterwarnings("ignore")
exec(open("port_risk2.py").read().split("GRID = [")[0])
from lv_wf import load_dir, select
use_pool(PC); WB0 = W_abs(-3, 22)
BASE = build2(NEWL)
CANDS = [("HTF-уровни", "lv2", "lv_engine", "fam <= 22", "div_lv2_1537_sc.npz", 4),
         ("профиль объёма", "lv5", "lv5_engine", "fam <= 5", "div_lv5_7686_sc.npz", 4),
         ("классика ev3", "ev3", "ev3_engine", "fam >= 0", "div_ev3_3690_sc.npz", 4)]
ROWS = {}
for nm, dr, eng, mexpr, scf, mid in CANDS:
    LX = importlib.import_module(eng); Dd = load_dir(dr, LX.FNAMES); Fv = Dd["F"]; fam = Fv[:, 0].astype(int); Tv = Dd["T"]
    dcol = list(LX.FNAMES).index("datr")
    gm = eval(mexpr); z = np.load(scf, allow_pickle=True); SC = z["SC"]; THR = z["THR"].item()
    s = select(Dd, 2, SC, THR, 0.995, 12, gm); s = s[Tv[s] >= ts(2022)]
    out = []
    for i in s:
        stp = float(Fv[i, dcol]) / 100
        out.append((float(Tv[i]), float(Tv[i] + Dd["K"][2][i] * 3600), float(Dd["R"][2][i]), stp, stp, 1.5, mid, cid(Dd["names"][Dd["SYM"][i]]), 1.0, 1e18))
    ROWS[nm] = np.array(out, float); del Dd
    print(f"{nm}: сделок {len(out)} ср.R {ROWS[nm][:, 2].mean():+.3f} стоп медиана {np.median(ROWS[nm][:, 3])*100:.1f}%", flush=True)
recent = roll2 >= ts(2024, 12)
def wins(A, rk, fr):
    A = A[np.argsort(A[:, 0], kind="stable")]
    t0, t1, r_, st_, sth, buf, md, ci, wg, tbr = A.T; md = md.astype(np.int64); ci = ci.astype(np.int64)
    if fr: r_ = np.where(md != 0, r_ - 0.03, r_)
    use = np.ones(5, np.bool_); rk_ = np.array(rk, float) / 100
    f = lambda a, b: simx(t0, t1, r_, st_, sth, buf, md, ci, use, rk_, int(np.searchsorted(t0, a)), b, 0.05, wg, 10.0, 20.0, 0.9, 20.0, tbr)
    Y = [f(s_, s_ + 365 * 86400.0) for s_ in roll2]
    return np.array([v[0] for v in Y]), np.array([v[1] for v in Y]), f(ts(2025, 10), ts(2026, 10))[0], f(ts(2026, 1), ts(2026, 10))[0]
RB = [4.5, 3, 2.5, 2]
for fr in (False, True):
    b, bd, bl, b26 = wins(BASE, RB + [0], fr)
    print(f"== {'с издержками' if fr else 'как в бэктесте'}: сейчас медиана ${np.median(b):,.0f} 10% ${np.percentile(b, 10):,.0f} просадка {np.median(bd)*100:.0f}% 12 мес ${bl:,.0f} 2026 ${b26:,.0f}", flush=True)
    combos = [(nm, [nm]) for nm, *_ in CANDS] + [("все три", [c[0] for c in CANDS]), ("HTF + профиль", ["HTF-уровни", "профиль объёма"])]
    for cn, members in combos:
        for rk in (1.0, 2.0, 3.0):
            rr = RB + [rk]
            A = np.vstack([BASE] + [ROWS[m] for m in members])
            y, dd, l, l26 = wins(A, rr, fr)
            q = y / b
            print(f"   + {cn:16s} {rk}%: медиана ${np.median(y):>7,.0f} 10% ${np.percentile(y, 10):>6,.0f} просадка {np.median(dd)*100:.0f}% | 12 мес ${l:>8,.0f} 2026 ${l26:>7,.0f} | окон лучше {np.mean(q > 1)*100:.0f}% ×{np.median(q):.2f} | с дек.2024: лучше {np.mean(q[recent] > 1)*100:.0f}% ×{np.median(q[recent]):.2f} (худшее ×{q[recent].min():.2f})", flush=True)
