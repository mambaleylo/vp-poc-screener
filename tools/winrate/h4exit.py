"""4h wick1 (E1 model, q0.99): the same selected limit fills, exits swept (stop x take x hold); per exit: train / unseen
(127 check + 83 new) R and WR, per year, the last 12 months; then the money sim (up to 20 at 3%) on all 210 coins"""
import numpy as np, pickle, os, warnings; warnings.filterwarnings("ignore")
import pool as PL
from s15_wf import load, select
from mk import ts
import importlib
E = importlib.import_module("s20h4_engine")
Q = 0.99
def fills():
    if os.path.exists("h4fills.pkl"): return pickle.load(open("h4fills.pkl", "rb"))
    out = []
    z = np.load("s20h4_sc_wick1_1.npz", allow_pickle=True); THR = z["THR"].item()
    for dr, SC, part in (("s20h4", z["SC"], None), ("s20h4x", np.load("s20h4x_sc_wick1_1.npy"), "new")):
        U = load(dr, [E.FAMS.index("wick1")])
        ok = np.array([U["names"][k] != "USDCUSDT" for k in U["sym"]])
        s_ = select(U, 1, SC, THR, Q, 12, ok); s_ = s_[U["t"][s_] >= ts(2022)]
        by = {}
        for i in s_: by.setdefault(U["sym"][i], []).append(i)
        for k, idx in by.items():
            sym = U["names"][k]; Tb, O, H, L, C, V = E.load15(sym); atr = E.wilder(H, L, C, 14); pos = {int(t): j for j, t in enumerate(Tb)}
            for ev in idx:
                s = int(U["side"][ev]); i = pos[int(U["t"][ev])]; a = float(atr[i]); lv = (L[i] if s > 0 else H[i]) - s * a
                fb = next((b for b in range(i + 1, min(i + 5, len(C))) if ((L[b] <= lv) if s > 0 else (H[b] >= lv))), -1)
                if fb < 0: continue
                fill = min(lv, O[fb]) if s > 0 else max(lv, O[fb])
                pt = part or ("check" if U["chk"][ev] else "train")
                out.append((sym, fb, s, fill, a, int(Tb[fb]), pt))
    pickle.dump(out, open("h4fills.pkl", "wb")); return out
F = fills()
print("сделок", len(F), flush=True)
cache = {}
def bars(sym):
    if sym not in cache: cache[sym] = E.load15(sym)
    return cache[sym]
STOPS = (1.0, 1.5, 2.0, 2.5, 3.0); TAKES = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0); HOLDS = (16, 32, 48)
res = {}
for st in STOPS:
    for tk in TAKES:
        for hd in HOLDS:
            rows = []
            for sym, fb, s, fill, a, t, pt in F:
                Tb, O, H, L, C, V = bars(sym)
                r, kk, w = PL.sim(O, H, L, C, fb, s, fill, a, tk, st, hd, 6.0)
                rows.append((t, t + kk * 14400, float(r), st * a / fill, pt, w))
            res[(st, tk, hd)] = rows
pickle.dump(res, open("h4exit.pkl", "wb"))
def summ(rows):
    R = np.array([r[2] for r in rows]); W = np.array([r[5] for r in rows]); t = np.array([r[0] for r in rows])
    return R, W, t
lines = []
for key, rows in res.items():
    tr = [r for r in rows if r[4] == "train"]; un = [r for r in rows if r[4] != "train"]
    Rt, Wt, _ = summ(tr); Ru, Wu, tu = summ(un)
    ys = " ".join(f"{Ru[(tu>=ts(Y))&(tu<ts(Y+1))].mean():+.2f}" for Y in range(2022, 2027))
    h = tu >= ts(2025, 10)
    lines.append((Rt.mean(), f"стоп {key[0]} тейк {key[1]} держать {key[2]:2d}: обуч WR{Wt.mean()*100:3.0f}% {Rt.mean():+.3f}R | невид. WR{Wu.mean()*100:3.0f}% {Ru.mean():+.3f}R [{ys}] посл.12м {Ru[h].mean():+.3f}R"))
lines.sort(reverse=True)
for _, l in lines: print(l)
# money: the best 12 by the TRAIN R plus the current 2/1/32, up to 20 at 3%, all 210 coins
keys = [k for _, k in sorted(((np.mean([r[2] for r in res[k] if r[4] == "train"]), k) for k in res), reverse=True)[:12]]
if (2.0, 1.0, 32) not in keys: keys.append((2.0, 1.0, 32))
roll = np.arange(ts(2024), ts(2025, 10) + 1, 7 * 86400.0)
print("\nденьги: до 20 по 3%, все 210 монет, осторожно (−0.025R на сделку), старт $100, через 12 мес")
for k in keys:
    rows = sorted(res[k]); t0 = np.array([r[0] for r in rows], float); t1 = np.array([r[1] for r in rows], float)
    R = np.array([r[2] for r in rows]); ST = np.array([r[3] for r in rows])
    for rk in (0.03,):
        o = np.array([PL.multi(t0, t1, R, ST, int(np.searchsorted(t0, s)), s + 365 * 86400.0, 20, rk, False, -0.025) for s in roll]) + 100
        last = PL.multi(t0, t1, R, ST, int(np.searchsorted(t0, ts(2025, 10))), ts(2025, 10) + 365 * 86400.0, 20, rk, False, -0.025) + 100
        o6 = np.array([PL.multi(t0, t1, R, ST, int(np.searchsorted(t0, s)), s + 182 * 86400.0, 20, rk, False, -0.025) for s in roll]) + 100
        print(f"  стоп {k[0]} тейк {k[1]} держать {k[2]:2d}: посл.12м ${last:,.0f} | окна 2024-26 медиана ${np.median(o):,.0f}, хуже-10% ${np.percentile(o,10):,.0f}, ниже $100 {np.mean(o<100)*100:.0f}% | 6 мес медиана ${np.median(o6):,.0f}, ниже $100 {np.mean(o6<100)*100:.0f}%", flush=True)
