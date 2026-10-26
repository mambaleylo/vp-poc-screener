"""the bad year (p10 of the 12-month windows from $100) — each earlier research stream as a 6th module of the bundle as
deployed (⚡ 4.5, P/R 3, SMC 2.5, EMA 2, HTF 2): its own walk-forward model, E2 exit (stop 1 dATR, take 3R, 72 h),
q 0.995, cap 12 a side, every coin (lv_wf.select: the score order within an hour — optimistic, a screen only);
friction -0.03R; p10 / p25 / median, the mean of the worst 10%, the 2023 starts (the quiet year)"""
import numpy as np, warnings, importlib, gc; warnings.filterwarnings("ignore")
exec(open("htf_money5.py").read().split("L = [(k")[0])
from lv_wf import load_dir, select
s2 = src.replace("nmod = np.zeros(5); rmod = np.zeros(5)", "nmod = np.zeros(6); rmod = np.zeros(6)").replace("def simx(", "def sim6(")
exec(s2)
H = rows("htf_bt_v1.json")
CANDS = [("iFVG", "lv7", "lv7_engine", "(fam % 6 == 2) | (fam % 6 == 3)", "ifvg_sc.npz"),
         ("SMC 8h/12h", "lv8", "lv8_engine", "(fam >= 6) & (fam <= 17)", "SMC8h12h_sc.npz"),
         ("деривативы", "ev2", "ev2_engine", "fam >= 0", "div_ev2_3690_sc.npz"),
         ("GitHub ev4", "ev4", "ev4_engine", "fam >= 0", "div_ev4_3690_sc.npz"),
         ("классика ev3", "ev3", "ev3_engine", "fam >= 0", "div_ev3_3690_sc.npz"),
         ("профиль объёма", "lv5", "lv5_engine", "fam <= 5", "div_lv5_7686_sc.npz"),
         ("Фибоначчи", "lv5", "lv5_engine", "fam >= 6", "div_lv5_8655_sc.npz")]
q23 = (roll2 >= ts(2023, 1)) & (roll2 < ts(2024, 1))
def go(X, rk):
    X = X[np.argsort(X[:, 0], kind="stable")]
    t0, t1, r_, st_, sth, buf, md, ci, wg, tbr = X.T; md = md.astype(np.int64); ci = ci.astype(np.int64); r_ = np.where(md != 0, r_ - 0.03, r_)
    use = np.ones(6, np.bool_); rk_ = np.array(rk, float) / 100
    Y = [sim6(t0, t1, r_, st_, sth, buf, md, ci, use, rk_, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 0.05, wg, 10.0, 20.0, 0.9, 20.0, tbr) for s_ in roll2]
    return np.array([v[0] for v in Y]), np.array([v[1] for v in Y])
def show(nm, y, d, ref=None):
    w = np.sort(y)[:max(1, len(y) // 10)].mean()
    extra = "" if ref is None else f" | окон лучше {np.mean(y > ref)*100:3.0f}%, из 2023-х {np.mean(y[q23] > ref[q23])*100:3.0f}%"
    print(f"  {nm:30s} 10% ${np.percentile(y, 10):>6,.0f} 25% ${np.percentile(y, 25):>6,.0f} медиана ${np.median(y):>7,.0f} 90% ${np.percentile(y, 90):>8,.0f} | худшие 10% в ср. ${w:>6,.0f} | 2023-е старты мед ${np.median(y[q23]):>6,.0f} | просадка {np.median(d)*100:.0f}%{extra}", flush=True)
B = np.vstack([BASE, H])
ref, rd = go(B, [4.5, 3, 2.5, 2, 2.0, 0]); show("как сейчас", ref, rd)
for nm, dr, eng, mexpr, scf in CANDS:
    try:
        LX = importlib.import_module(eng); Dd = load_dir(dr, LX.FNAMES); Fv = Dd["F"]; fam = Fv[:, 0].astype(int); Tv = Dd["T"]
        dcol = list(LX.FNAMES).index("datr"); gm = eval(mexpr)
        z = np.load(scf, allow_pickle=True); SC = z["SC"]; THR = z["THR"].item()
        s = select(Dd, 2, SC, THR, 0.995, 12, gm); s = s[Tv[s] >= ts(2022)]
        X = np.array([(float(Tv[i]), float(Tv[i] + Dd["K"][2][i] * 3600), float(Dd["R"][2][i]), float(Fv[i, dcol]) / 100, float(Fv[i, dcol]) / 100, 1.5, 5,
                       cid(Dd["names"][Dd["SYM"][i]]), 1.0, 1e18) for i in s], float)
        r23 = X[(X[:, 0] >= ts(2023)) & (X[:, 0] < ts(2024)), 2]
        print(f"{nm}: сделок {len(X)}, ср.R {X[:, 2].mean():+.2f}, в 2023: {len(r23)} сделок ср.R {r23.mean():+.2f}", flush=True)
        np.save(f"quiet_{dr}_{nm.split()[0]}.npy", X)
        del Dd; gc.collect()
        for rk in (1.0, 2.0):
            y, d = go(np.vstack([B, X]), [4.5, 3, 2.5, 2, 2.0, rk]); show(f"+ {nm} {rk}%", y, d, ref)
    except Exception as e:
        print(nm, "ошибка", repr(e)[:200], flush=True)
