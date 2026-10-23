"""all the honest streams (127 coins, 2022-26): trades per stream with (fill time, exit time, R, stop share, coin set);
combos judged on the TRAIN coins (choice), then reported on the CHECK coins (never used for the choice): one trade at
a time with the "grow" ladder, and up to N at once with a fixed risk; 12 months from $100, the real order kept"""
import numpy as np, pickle, os, warnings; warnings.filterwarnings("ignore")
from numba import njit
from s15_wf import load, select
from mk import ts
import importlib
@njit
def sim(O, H, L, C, f, side, fill, atr, tk, st, hold, fund_div):
    n = len(C); risk = st * atr; sl = fill - side * risk; tp = fill + side * tk * atr
    e = min(n, f + hold); k = e - 1 - f; ex = C[e - 1]; win = 0; fout = 0.0005
    for q in range(e - f):
        b = f + q
        if (side > 0 and L[b] <= sl) or (side < 0 and H[b] >= sl):
            gap = (side > 0 and O[b] <= sl) or (side < 0 and O[b] >= sl)
            ex = O[b] if (gap and q > 0) else sl; k = q; break
        if q > 0 and ((side > 0 and H[b] >= tp) or (side < 0 and L[b] <= tp)):
            ex = tp; k = q; win = 1; fout = 0.0002; break
    return (side * (ex - fill) - (0.0002 + fout + 0.0003 * (k + 1) / fund_div) * fill) / risk, k + 1, win
def level(fam, C, L, H, atr, a28, i, s):
    return {"d2": C[i] - s * 2 * atr[i], "d15": C[i] - s * 1.5 * atr[i], "wick1": (L[i] if s > 0 else H[i]) - s * atr[i], "d2a28": C[i] - s * 2 * a28[i]}[fam]
def stream(mod, dr, fam, scfile, e, q, tk, hold, bar_s, fund_div, scname="SC", thrname="THR"):
    E = importlib.import_module(mod)
    fams = getattr(E, "FAMS", ["d2"])
    U = load(dr, [fams.index(fam) if fam in fams else 0]); z = np.load(scfile, allow_pickle=True); SC, THR = z[scname], z[thrname].item()
    out = []
    for setname, sub in (("train", ~U["chk"]), ("check", U["chk"])):
        s_ = select(U, e, SC, THR, q, 12, sub); s_ = s_[U["t"][s_] >= ts(2022)]
        by = {}
        for i in s_: by.setdefault(U["sym"][i], []).append(i)
        for k, idx in by.items():
            Tb, O, H, L, C, V = E.load15(U["names"][k]); atr = E.wilder(H, L, C, 14); a28 = E.wilder(H, L, C, 28); pos = {int(t): j for j, t in enumerate(Tb)}
            for ev in idx:
                s = int(U["side"][ev]); i = pos[int(U["t"][ev])]; a = float(atr[i]); lv = level(fam, C, L, H, atr, a28, i, s)
                fb = next((b for b in range(i + 1, min(i + 5, len(C))) if ((L[b] <= lv) if s > 0 else (H[b] >= lv))), -1)
                if fb < 0: continue
                fill = min(lv, O[fb]) if s > 0 else max(lv, O[fb])
                r, kk, w = sim(O, H, L, C, fb, s, fill, a, tk, 2.0, hold, fund_div)
                out.append((int(Tb[fb]), int(Tb[fb]) + kk * bar_s, float(r), 2 * a / fill, setname, w))
    return out
SPEC = {
    "15м 2ATR т1.25": ("s15u_engine", "s15u", "d2", "s15u_sc_e1.npz", 1, 0.99, 1.25, 32, 900, 96.0),
    "30м 2×ATR28 т1": ("s22m30_engine", "s22m30", "d2a28", "s22m30_sc_d2a28_1.npz", 1, 0.99, 1.0, 32, 1800, 48.0),
    "30м 1.5ATR т1": ("s22m30_engine", "s22m30", "d15", "s22m30_sc_d15_1.npz", 1, 0.99, 1.0, 32, 1800, 48.0),
    "1ч 2×ATR28 т1.5": ("s19h_engine", "s19h", "d2a28", "s19h_sc_d2a28_1.npz", 1, 0.98, 1.5, 32, 3600, 24.0),
    "1ч тень т1": ("s19h_engine", "s19h", "wick1", "s19h_sc_wick1_1.npz", 1, 0.98, 1.0, 32, 3600, 24.0),
    "2ч 2ATR т1": ("s21h2_engine", "s21h2", "d2", "s21h2_sc_d2_1.npz", 1, 0.99, 1.0, 32, 7200, 12.0),
    "2ч тень т1": ("s21h2_engine", "s21h2", "wick1", "s21h2_sc_wick1_1.npz", 1, 0.99, 1.0, 32, 7200, 12.0),
    "4ч тень т0.5": ("s20h4_engine", "s20h4", "wick1", "s20h4_sc_wick1_0.npz", 0, 0.99, 0.5, 16, 14400, 6.0),
    "4ч 1.5ATR т0.5": ("s20h4_engine", "s20h4", "d15", "s20h4_sc_d15_0.npz", 0, 0.99, 0.5, 16, 14400, 6.0),
    "4ч тень т1": ("s20h4_engine", "s20h4", "wick1", "s20h4_sc_wick1_1.npz", 1, 0.99, 1.0, 32, 14400, 6.0),
}
if os.path.exists("pool.pkl"):
    P = pickle.load(open("pool.pkl", "rb"))
else:
    P = {}
    for nm, sp in SPEC.items():
        P[nm] = stream(*sp); print(nm, len(P[nm]), np.mean([x[2] for x in P[nm]]), flush=True)
    pickle.dump(P, open("pool.pkl", "wb"))
@njit
def multi(t0, t1, R, ST, i0, tend, maxpos, risk_fixed, ladder, shift):
    eq = 1.0; K = 1.0; deps = 1.0; wd = 0.0
    po_t = np.zeros(maxpos); po_r = np.zeros(maxpos); po_m = np.zeros(maxpos); po_u = np.zeros(maxpos); on = np.zeros(maxpos, np.bool_)
    j = i0
    while j < len(t0) and t0[j] < tend:
        for k in range(maxpos):
            if on[k] and po_t[k] <= t0[j]:
                eq += po_u[k] * (po_r[k] + shift); on[k] = False
        if eq < 0.1:
            eq = 1.0; K = 1.0; deps += 1.0
            for k in range(maxpos): on[k] = False
        elif ladder and eq >= 5 * K and not on.any():
            w = (eq - K) / 2; wd += w; eq -= w; K = eq
        slot = -1; used = 0.0
        for k in range(maxpos):
            if on[k]: used += po_m[k]
            elif slot < 0: slot = k
        if slot >= 0:
            st = ST[j]; lev = min(20.0, np.floor(1.0 / (1.5 * st + 0.0105)))
            rk = risk_fixed if not ladder else (0.5 if eq < 3 else (0.3 if eq < 10 else 0.15))
            ru = eq * rk; m = ru / st / lev; free = (eq - used) * 0.9
            if m > free:
                if free <= 0.0: ru = 0.0
                else: ru *= free / m; m = free
            if ru > 0:
                on[slot] = True; po_t[slot] = t1[j]; po_r[slot] = R[j]; po_m[slot] = m; po_u[slot] = ru
        j += 1
    for k in range(maxpos):
        if on[k]: eq += po_u[k] * (po_r[k] + shift)
    return (wd + max(eq, 0.0) - deps) * 100
MODES = [(1, 0.0, True, "одна, лесенка"), (5, 0.05, False, "до 5 по 5%"), (5, 0.10, False, "до 5 по 10%"), (8, 0.07, False, "до 8 по 7%")]
def money(rows, mode, shift, n=500):
    rows = sorted(rows); t0 = np.array([r[0] for r in rows], float); t1 = np.array([r[1] for r in rows], float)
    R = np.array([r[2] for r in rows]); ST = np.array([r[3] for r in rows])
    last = np.searchsorted(t0, t0[-1] - 365 * 86400)
    if last < 10: return np.nan, np.nan
    starts = np.random.default_rng(3).integers(0, last, n)
    mp, rf, lad, _ = mode
    o = np.array([multi(t0, t1, R, ST, int(i), t0[i] + 365 * 86400.0, mp, rf, lad, shift) for i in starts])
    return float(np.median(o)), float(np.mean(o < 0))
if __name__ == "__main__":
    names = list(SPEC)
    for nm in names:
        tr = [r for r in P[nm] if r[4] == "train"]; ch = [r for r in P[nm] if r[4] == "check"]
        print(f"{nm:18s} обуч n {len(tr):5d} WR {np.mean([r[5] for r in tr])*100:.0f}% {np.mean([r[2] for r in tr]):+.3f}R | пров n {len(ch):5d} WR {np.mean([r[5] for r in ch])*100:.0f}% {np.mean([r[2] for r in ch]):+.3f}R", flush=True)
    # greedy forward selection on the TRAIN coins, the score = the cautious median of the best mode
    def score(sel, part):
        rows = [r for nm in sel for r in P[nm] if r[4] == part]
        best = None
        for md in MODES:
            med, neg = money(rows, md, -0.025, 300)
            if best is None or med > best[0]: best = (med, neg, md[3])
        return best
    chosen = []; cur = None
    while True:
        cand = []
        for nm in names:
            if nm in chosen: continue
            sc = score(chosen + [nm], "train"); cand.append((sc[0], nm, sc))
        cand.sort(reverse=True)
        if not cand or (cur is not None and cand[0][0] <= cur[0] * 1.03): break
        chosen.append(cand[0][1]); cur = cand[0][2]
        print(f"+ {cand[0][1]:18s} → обуч (осторожно) медиана ${cur[0]:.0f} минус {cur[1]*100:.0f}% [{cur[2]}]", flush=True)
    print("\nвыбрано:", chosen)
    for part in ("train", "check"):
        rows = [r for nm in chosen for r in P[nm] if r[4] == part]
        for md in MODES:
            b = money(rows, md, 0.0); c = money(rows, md, -0.025); h = money(rows, md, -0.04)
            print(f"  {part:5s} {md[3]:14s} бэктест ${b[0]:7.0f} ({b[1]*100:.0f}%) · осторожно ${c[0]:7.0f} ({c[1]*100:.0f}%) · жёстко ${h[0]:7.0f} ({h[1]*100:.0f}%)", flush=True)
    rows = [r for nm in chosen for r in P[nm]]
    for md in MODES:
        b = money(rows, md, 0.0); c = money(rows, md, -0.025); h = money(rows, md, -0.04)
        print(f"  все   {md[3]:14s} бэктест ${b[0]:7.0f} ({b[1]*100:.0f}%) · осторожно ${c[0]:7.0f} ({c[1]*100:.0f}%) · жёстко ${h[0]:7.0f} ({h[1]*100:.0f}%)", flush=True)
