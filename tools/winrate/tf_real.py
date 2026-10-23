"""1m check (40 coins, 2024-10+) of the honest 1h families (E1 model): exits incl. take ladders; fill 0.05% through;
WR = the first take reached"""
import os, numpy as np, warnings; warnings.filterwarnings("ignore")
from numba import njit
import importlib, sys
AV = list(sys.argv); MOD, DR, SEC = AV[1], AV[2], int(AV[3])
E = importlib.import_module(MOD)
from s15_wf import load, select
from mk import ts
@njit
def sim(O, H, L, C, f, side, fill, atr, tks, frs, st, hold, fin):
    n = len(C); risk = st * atr; sl = fill - side * risk
    e = min(n, f + hold); left = 1.0; pnl = 0.0; fees = fin * fill; first = 0; nxt = 0; k_end = e - 1 - f
    for q in range(e - f):
        b = f + q
        if (side > 0 and L[b] <= sl) or (side < 0 and H[b] >= sl):
            gap = (side > 0 and O[b] <= sl) or (side < 0 and O[b] >= sl)
            ex = O[b] if (gap and q > 0) else sl
            pnl += left * side * (ex - fill); fees += left * 0.0005 * fill; left = 0.0; k_end = q; break
        if q > 0:
            while nxt < len(tks):
                tp = fill + side * tks[nxt] * atr
                if (side > 0 and H[b] >= tp) or (side < 0 and L[b] <= tp):
                    pnl += frs[nxt] * side * (tp - fill); fees += frs[nxt] * 0.0002 * fill; left -= frs[nxt]; nxt += 1; first = 1
                else: break
            if left <= 1e-9: k_end = q; break
    if left > 1e-9:
        pnl += left * side * (C[e - 1] - fill); fees += left * 0.0005 * fill
    fees += 0.0003 * (k_end + 1) / 1440.0 * fill
    return (pnl - fees) / risk, first
EX = [("тейк 0.5 ATR, 16 свечей", [0.5], [1.0], 16), ("тейк 1 ATR, 32 свечи", [1.0], [1.0], 32), ("тейк 1.5 ATR, 32 свечи", [1.5], [1.0], 32)]
avail = {f[:-4] for f in os.listdir("data/1mz")}
for fam, EM in [tuple([a.split(":")[0], int(a.split(":")[1])]) for a in AV[4:]]:
    U = load(DR, [E.FAMS.index(fam)])
    z = np.load(os.environ.get("SCF") or f"{DR}_sc_{fam}_{EM}.npz", allow_pickle=True); SC, THR = z["SC"], z["THR"].item()
    for q in (0.98, 0.99):
        res15 = {v: [] for v in range(len(EX))}; res1 = {v: [] for v in range(len(EX))}
        for sub in (~U["chk"], U["chk"]):
            s_ = select(U, EM, SC, THR, q, int(os.environ.get("CAP", "12")), sub); s_ = s_[U["t"][s_] >= ts(2022)]
            by = {}
            for i in s_: by.setdefault(U["sym"][i], []).append(i)
            for k, idx in by.items():
                sym = U["names"][k]
                Tb, O, H, L, C, V = E.load15(sym); atr = E.wilder(H, L, C, 14); a28 = E.wilder(H, L, C, 28); pos = {int(t): j for j, t in enumerate(Tb)}
                one = None
                if sym in avail:
                    qd = np.load(f"data/1mz/{sym}.npz"); one = (qd["t"], qd["o"], qd["h"], qd["l"], qd["c"])
                for ev in idx:
                    s = int(U["side"][ev]); i = pos[int(U["t"][ev])]; a = float(atr[i])
                    lv = {"d2": C[i] - s * 2 * a, "d15": C[i] - s * 1.5 * a, "wick1": (L[i] if s > 0 else H[i]) - s * a, "w1": (L[i] if s > 0 else H[i]) - s * a, "d2a28": C[i] - s * 2 * a28[i]}[fam]
                    fb = next((b for b in range(i + 1, min(i + 5, len(C))) if ((L[b] <= lv) if s > 0 else (H[b] >= lv))), -1)
                    if fb < 0: continue
                    fill = min(lv, O[fb]) if s > 0 else max(lv, O[fb])
                    for v, (nm, tks, frs, hd) in enumerate(EX):
                        res15[v].append(sim(O, H, L, C, fb, s, fill, a, np.array(tks), np.array(frs), 2.0, hd, 0.0002) if True else 0)
                    if one is None or Tb[i] < ts(2024, 10): continue
                    t1, o1, h1, l1, c1 = one
                    j0 = np.searchsorted(t1, Tb[i] + SEC)
                    M = SEC // 60
                    if j0 + 4 * M + 32 * M >= len(t1) or t1[j0] != Tb[i] + SEC: continue
                    thr_ = lv * (1 - s * 0.0005)
                    hit = np.flatnonzero((l1[j0:j0 + 4 * M] <= thr_) if s > 0 else (h1[j0:j0 + 4 * M] >= thr_))
                    if not len(hit): continue
                    f = j0 + int(hit[0]); fl = min(lv, o1[f]) if s > 0 else max(lv, o1[f])
                    for v, (nm, tks, frs, hd) in enumerate(EX):
                        res1[v].append(sim(o1, h1, l1, c1, f, s, fl, a, np.array(tks), np.array(frs), 2.0, hd * M, 0.0002))
        print(f"\n##### {DR} {fam}, модель E{EM}, лучшие {round((1-q)*100)}%")
        for v, (nm, *_ ) in enumerate(EX):
            a15 = np.array(res15[v]); a1 = np.array(res1[v])
            print(f"  {nm:34s} история WR {a15[:,1].mean()*100:4.1f}% {a15[:,0].mean():+.3f}R (n {len(a15)}) || 1м сквозь WR {a1[:,1].mean()*100:4.1f}% {a1[:,0].mean():+.3f}R (n {len(a1)})", flush=True)
