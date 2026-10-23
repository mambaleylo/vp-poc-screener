"""the user: "если цена не прошла в сторону стопа n, а сразу пошла к тейку — увеличить тейк на n". The deployed ⚡ pool (4h
wick + 2h close): when the price reaches the take (1 ATR) and has never gone against the trade by n ATR since the fill,
the take moves to 1 + e ATR (e = n, or fixed); the stop then stays (2 ATR), goes to the entry, or locks +0.5 ATR.
Bar level, the worst order inside a bar: a touch bar whose low (a long) went n ATR against does not qualify; after the
move the new stop is checked in the touch bar too (the dip may come after the touch), the new take only from the next
bar. The pool as the bot trades it (exits change the busy times), money at 20 positions x 4%"""
import os; os.environ["TFH"] = "4"
import numpy as np, warnings, importlib; warnings.filterwarnings("ignore")
from numba import njit
exec(open("best_money.py").read().split("za = np.load")[0])
exec(open("pool2h.py").read().split("def stream")[0].split("import importlib")[1])   # merged()
def events(dr, fi, scf, eng, tfh, anchor, depth, q=0.99):
    os.environ["TFH"] = str(tfh); E = importlib.import_module(eng)
    X = merged(dr, fi); z = np.load(scf, allow_pickle=True); SC, THR = z["SC"], z["THR"].item(); T = X["t"]
    yr = T.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970; thr = np.full(len(T), np.inf)
    for Y, v in THR.items(): thr[yr == Y] = np.quantile(v, q)
    out = []
    for i in np.flatnonzero(~X["usdc"] & np.isfinite(SC) & (SC >= thr) & (T >= ts(2022))):
        sym = X["names"][X["sym"][i]]; s = int(X["side"][i]); t = int(T[i])
        if (sym, tfh) not in BARS:
            Tb, O, H, L, C, V = E.load15(sym); BARS[(sym, tfh)] = (Tb, O, H, L, C, E.wilder(H, L, C, 14), {int(x): j for j, x in enumerate(Tb)})
        Tb, O, H, L, C, atr, pos = BARS[(sym, tfh)]; bi = pos[t]; a = float(atr[bi])
        lv = ((L[bi] if s > 0 else H[bi]) if anchor == "wick" else C[bi]) - s * depth * a
        fb = next(b for b in range(bi + 1, bi + 5) if ((L[b] <= lv) if s > 0 else (H[b] >= lv)))
        fill = min(lv, O[fb]) if s > 0 else max(lv, O[fb])
        out.append(dict(lv=lv, ft=int(Tb[fb]), nsc=-float(SC[i]), t=t, sym=sym, s=s, tfh=tfh, fb=fb, fill=fill, a=a, r0=float(X["R"][1 if tfh == 2 else 0][i])))
    return out
BARS = {}
EV = events("s23_4h", 2, "s26_s23_4h_w1_0.npz", "s23_engine", 4, "wick", 1.0) + events("s21h2", 0, "s26_s21h2_d2_1.npz", "s21h2_engine", 2, "close", 2.0)
print("events", len(EV), flush=True)
@njit
def ex(O, H, L, C, f, s, fill, a, n, e, smode, tfh):
    """-> R (per the 2 ATR risk), kind (1 take / 2 extended take / 0 stop / 3 time / 4 the moved stop), bars"""
    N = len(C); end = min(N, f + 32); risk = 2.0 * a; sl = fill - s * risk; tp = fill + s * a; mae = 0.0; ext = False; tp2 = 0.0
    for q in range(end - f):
        b = f + q
        adv = (fill - L[b]) if s > 0 else (H[b] - fill)
        if (s > 0 and L[b] <= sl) or (s < 0 and H[b] >= sl):
            gap = (s > 0 and O[b] <= sl) or (s < 0 and O[b] >= sl)
            x = O[b] if (gap and q > 0) else sl
            k = 4 if ext and smode > 0 else 0
            return (s * (x - fill) - (0.0007 + 0.0003 * (q + 1) * tfh / 24) * fill) / risk, k, q
        if ext:
            if (s > 0 and H[b] >= tp2) or (s < 0 and L[b] <= tp2):
                return (s * (tp2 - fill) - (0.0004 + 0.0003 * (q + 1) * tfh / 24) * fill) / risk, 2, q
        elif q > 0 and ((s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp)):
            if max(mae, adv) < n * a and n > 0:
                ext = True; tp2 = fill + s * (1.0 + e) * a
                if smode == 1: sl = fill
                elif smode == 2: sl = fill + s * 0.5 * a
                if smode > 0 and ((s > 0 and L[b] <= sl) or (s < 0 and H[b] >= sl)):   # the worst order: the dip after the touch
                    return (s * (sl - fill) - (0.0007 + 0.0003 * (q + 1) * tfh / 24) * fill) / risk, 4, q
            else:
                return (s * (tp - fill) - (0.0004 + 0.0003 * (q + 1) * tfh / 24) * fill) / risk, 1, q
        if adv > mae: mae = adv
    return (s * (C[end - 1] - fill) - (0.0007 + 0.0003 * (end - f) * tfh / 24) * fill) / risk, 3, end - 1 - f
def run(n, e, smode):
    rows = []
    for v in EV:
        Tb, O, H, L, C, atr, pos = BARS[(v["sym"], v["tfh"])]
        R, k, kk = ex(O, H, L, C, v["fb"], v["s"], v["fill"], v["a"], n, e, smode, v["tfh"])
        rows.append((v["ft"], v["nsc"], v["t"], v["sym"], v["s"], int(Tb[v["fb"] + kk]) + v["tfh"] * 3600, R, float(np.clip(2 * v["a"] / v["fill"], 0.002, 0.5)), k))
    rows.sort(key=lambda x: (x[0], x[1], x[2])); busy, act, P = {}, [], []
    for ft, nsc, t, sym, s, end, R, st, k in rows:
        if busy.get((sym, s), 0) > ft: continue
        act = [x for x in act if x[0] > ft]
        if sum(1 for x in act if x[1] == s) >= 20: continue
        busy[(sym, s)] = end; act.append((end, s)); P.append((ft, end, R, st, k))
    P.sort(key=lambda x: x[0]); return np.array(P, float)
roll = np.arange(ts(2024), ts(2025, 10) + 1, 7 * 86400.0)
def show(nm, n, e, sm):
    P = run(n, e, sm); t0, t1, R, STv, K = P[:, 0], P[:, 1], P[:, 2], P[:, 3], P[:, 4]
    y = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.025) for s_ in roll])
    yh = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.04)[0] for s_ in roll])
    h = t0 >= ts(2025, 10); wr = np.isin(K, (1, 2)).mean() * 100
    print(f"{nm:38s} n{len(R)} {R.mean():+.3f}R (посл.12м {R[h].mean():+.3f}) WR {wr:.0f}% | продлено {np.isin(K, (2, 4)).mean()*100:.0f}% "
          f"(дошли до нового тейка {(K == 2).mean()*100:.0f}%, выбило новым стопом {(K == 4).mean()*100:.0f}%) | медиана ${np.median(y[:, 0]):,.0f} "
          f"10% ${np.percentile(y[:, 0], 10):,.0f} просадка {np.median(y[:, 1])*100:.0f}%/{np.percentile(y[:, 1], 90)*100:.0f}% | жёстко ${np.median(yh):,.0f}", flush=True)
show("как сейчас (тейк 1 ATR)", 0, 0, 0)
SM = {0: "стоп прежний", 1: "стоп в безубыток", 2: "стоп +0.5 ATR"}
for n in (0.25, 0.5, 0.75, 1.0):
    for e in sorted({n, 0.5, 1.0}):
        for sm in (0, 1, 2):
            show(f"n={n} → тейк +{e} ATR, {SM[sm]}", n, e, sm)
