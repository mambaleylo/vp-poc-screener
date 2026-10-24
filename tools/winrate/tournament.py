"""the honest tournament (after the audit, the user: "не выбрали ли мы эту модель из-за твоих ошибок?"): every stream
with scores (s26 walk-forward, q0.99) alone and next to the 4h wick, the v0.99.690 take, the pool in the honest order
(the touch's 1h bar, the nearer level first, busy per coin & side, 20 a side), money at 20 positions; the risk for the
best ones"""
import os; os.environ["TFH"] = "4"
import numpy as np, warnings, importlib, glob; warnings.filterwarnings("ignore")
from s15_wf import load
from numba import njit
exec(open("best_money.py").read().split("za = np.load")[0])
exec("def merged" + open("dlm4_export4.py").read().split("def merged")[1].split("out_streams, EV, FN")[0])
exec("@njit\ndef ex" + open("tkext.py").read().split("@njit\ndef ex")[1].split("\ndef run")[0])
import s19h_engine as E1
H1 = {}
def h1(sym):
    if sym not in H1:
        T, O, H, L, C, V = E1.load15(sym); H1[sym] = (T.astype(np.int64), O, H, L)
    return H1[sym]
def events(dr, fi, scf, eng, tfh, anchor, depth, q=0.99):
    os.environ["TFH"] = str(tfh); E = importlib.import_module(eng)
    X = merged(dr, fi); z = np.load(scf, allow_pickle=True); SC, THR = z["SC"], z["THR"].item(); T = X["t"]
    yr = T.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970; thr = np.full(len(T), np.inf)
    for Y, v in THR.items(): thr[yr == Y] = np.quantile(v, q)
    out, cache = [], {}
    for i in np.flatnonzero(~X["usdc"] & np.isfinite(SC) & (SC >= thr) & (T >= ts(2022))):
        sym = X["names"][X["sym"][i]]; s = int(X["side"][i]); t = int(T[i])
        if sym not in cache:
            Tb, O, H, L, C, V = E.load15(sym); cache[sym] = (Tb, O, H, L, C, E.wilder(H, L, C, 14), E.wilder(H, L, C, 28), {int(x): j for j, x in enumerate(Tb)})
        Tb, O, H, L, C, atr, a28, pos = cache[sym]; bi = pos[t]; a = float(atr[bi])
        lv = ((L[bi] if s > 0 else H[bi]) if anchor == "wick" else C[bi]) - s * depth * (float(a28[bi]) if anchor == "a28" else a)
        fb = next((b for b in range(bi + 1, bi + 5) if ((L[b] <= lv) if s > 0 else (H[b] >= lv))), -1)
        if fb < 0: continue
        fill = min(lv, O[fb]) if s > 0 else max(lv, O[fb])
        R, k, kk = ex(O, H, L, C, fb, s, fill, a, 0.4, 1.0, 0, tfh)
        T1, O1, H1_, L1 = h1(sym); j0, j1 = int(np.searchsorted(T1, Tb[fb])), int(np.searchsorted(T1, Tb[fb] + tfh * 3600))
        ft1, d1 = int(Tb[fb]), 0.0
        for b in range(j0, j1):
            if (L1[b] <= lv) if s > 0 else (H1_[b] >= lv): ft1 = int(T1[b]); d1 = s * (O1[b] - lv) / a; break
        out.append(dict(key=(ft1, d1, -float(SC[i]), t), sym=sym, s=s, end=int(Tb[min(len(Tb) - 1, fb + kk)]) + tfh * 3600, R=float(R),
                        st=float(np.clip(2 * a / fill, 0.002, 0.5))))
    return out
S = {"4ч тень 1 (сейчас)": ("s23_4h", 2, "s26_s23_4h_w1_0.npz", "s23_engine", 4, "wick", 1.0),
     "4ч тень 0.75": ("s23_4h", 1, "s26_s23_4h_w075_0.npz", "s23_engine", 4, "wick", 0.75),
     "4ч тень 1.25": ("s23_4h", 3, "s26_s23_4h_w125_0.npz", "s23_engine", 4, "wick", 1.25),
     "4ч закр 2": ("s20h4", 0, "s26_s20h4_d2_1.npz", "s20h4_engine", 4, "close", 2.0),
     "4ч закр 1.5": ("s20h4", 1, "s26_s20h4_d15_1.npz", "s20h4_engine", 4, "close", 1.5),
     "4ч закр 2 ATR28": ("s20h4", 3, "s26_s20h4_d2a28_1.npz", "s20h4_engine", 4, "a28", 2.0),
     "2ч закр 2 (сейчас)": ("s21h2", 0, "s26_s21h2_d2_1.npz", "s21h2_engine", 2, "close", 2.0),
     "2ч тень 1": ("s21h2", 2, "s26_s21h2_wick1_1.npz", "s21h2_engine", 2, "wick", 1.0),
     "1ч тень 1": ("s19h", 2, "s26_s19h_wick1_1.npz", "s19h_engine", 1, "wick", 1.0),
     "1ч закр 2 ATR28": ("s19h", 3, "s26_s19h_d2a28_1.npz", "s19h_engine", 1, "a28", 2.0)}
EVS = {}
for nm, args in S.items():
    try:
        EVS[nm] = events(*args); print("loaded", nm, len(EVS[nm]), flush=True)
    except Exception as e:
        print("skip", nm, repr(e)[:120], flush=True)
roll = np.arange(ts(2024), ts(2025, 10) + 1, 7 * 86400.0)
def show(nm, evs, rk=0.04, cap=20):
    ev = sorted(evs, key=lambda e: e["key"]); busy, act, P = {}, [], []
    for e in ev:
        ft = e["key"][0]
        if busy.get((e["sym"], e["s"]), 0) > ft: continue
        act = [x for x in act if x[0] > ft]
        if sum(1 for x in act if x[1] == e["s"]) >= cap: continue
        busy[(e["sym"], e["s"])] = e["end"]; act.append((e["end"], e["s"])); P.append((ft, e["end"], e["R"], e["st"]))
    P = np.array(sorted(P), float); t0, t1, R, STv = P.T
    y = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, rk, -0.025) for s_ in roll])
    yh = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, rk, -0.04)[0] for s_ in roll])
    fx = []
    for st_ in ((2024, 1), (2024, 7), (2025, 1), (2025, 7), (2025, 10)):
        s_ = ts(*st_); v = sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0 if st_ < (2025, 10) else ts(2026, 10), 20, rk, -0.025)
        fx.append(f"{st_[0] % 100}.{st_[1]:02d}→${v[0]:,.0f}")
    yr = (t0 // 31557600 + 1970).astype(int)
    print(f"{nm:34s} {rk*100:.0f}% n{len(R)} {R.mean():+.3f}R [{' '.join(f'{y_ % 100}:{R[yr == y_].mean():+.2f}' for y_ in range(2023, 2027))}] | медиана ${np.median(y[:, 0]):,.0f} "
          f"10% ${np.percentile(y[:, 0], 10):,.0f} просадка {np.median(y[:, 1])*100:.0f}% | жёстко ${np.median(yh):,.0f} | " + " ".join(fx), flush=True)
    return np.median(y[:, 0])
print("== по отдельности")
for nm in EVS: show(nm, EVS[nm])
base = "4ч тень 1 (сейчас)"
print("== в паре с 4ч тень 1")
for nm in EVS:
    if nm != base: show(f"4ч + {nm}", EVS[base] + EVS[nm])
print("== риск")
for rk in (0.03, 0.05, 0.06):
    show("4ч одна", EVS[base], rk); show("4ч + 2ч закр (сейчас)", EVS[base] + EVS["2ч закр 2 (сейчас)"], rk)
