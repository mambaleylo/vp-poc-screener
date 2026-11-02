"""htf_repro.py's RL (the long HTF touches' traded exit: soft stop 1 dATR at a 4h close, hard 3 dATR, take 3R, 96 h) as a
function, cached to htf_rl.npy (rebuildable)"""
import os, glob, numpy as np
from numba import njit
import lv_engine as LE
from lv_wf import ts
@njit
def wk2(O, H, L, C, Tb, j, fill, datr, hard_a, take, hold, kh):
    risk = fill * datr / 100; ssl = fill - risk; hsl = fill - hard_a * risk; tp = fill + take * risk
    n = len(C); e = min(n, j + hold)
    for q in range(e - j):
        b = j + q
        if L[b] <= hsl:
            x = O[b] if (q > 0 and O[b] <= hsl) else hsl
            return (x - fill) / risk - (0.001 + 0.0003 * (q + 1) / 24) * fill / risk
        if q > 0 and H[b] >= tp:
            return (tp - fill) / risk - (0.001 + 0.0003 * (q + 1) / 24) * fill / risk
        if (Tb[b] + 3600) % (kh * 3600) == 0 and C[b] <= ssl:
            return (C[b] - fill) / risk - (0.001 + 0.0003 * (q + 1) / 24) * fill / risk
    b = e - 1
    return (C[b] - fill) / risk - (0.001 + 0.0003 * (e - j) / 24) * fill / risk
def load_ls(sym):
    """the lab-store's candles — the ones lv2's bar indices were built on (data/1h may now hold the 2020- files of dl.py)"""
    a = np.loadtxt(os.path.join(os.environ.get("LABSTORE", "/home/user/vp-lab-store"), "data", "1h", f"{sym}.csv.gz"), delimiter=",", ndmin=2)
    t = a[:, 0].astype(np.int64); k = np.concatenate([[True], np.diff(t) > 0]); a = a[k]
    return a[:, 0].astype(np.int64), a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5]
def rl(Dd, T, SIDE, fam, fn="htf_rl2.npy"):
    if os.path.exists(fn):
        x = np.load(fn)
        if len(x) == len(T): return x
    LV, J, DT = [], [], []
    for f in sorted(glob.glob("lv2/*.npz")):
        z = np.load(f)
        if len(z["t"]) == 0: continue
        LV.append(z["lv"]); J.append(z["j"]); DT.append(z["datr"])
    LV, J, DATR = np.concatenate(LV), np.concatenate(J).astype(np.int64), np.concatenate(DT)
    SYM = Dd["SYM"]; LONG = (fam <= 22) & (SIDE > 0) & (T >= ts(2019)) & np.isfinite(DATR)
    RL = np.full(len(T), np.nan); idx = np.flatnonzero(LONG)
    for k in sorted(set(SYM[idx])):
        Tb, O, H, L, C, V = load_ls(Dd["names"][k])
        ii = idx[SYM[idx] == k]; ok = J[ii] < len(Tb)
        assert (Tb[J[ii][ok]] == T[ii][ok]).mean() > 0.999, Dd["names"][k]   # the bar index points at the event's own hour
        for i in idx[SYM[idx] == k]:
            if J[i] < len(C): RL[i] = wk2(O, H, L, C, Tb, int(J[i]), float(LV[i]), float(DATR[i]), 3.0, 3.0, 96, 4)
    np.save(fn, RL); return RL
