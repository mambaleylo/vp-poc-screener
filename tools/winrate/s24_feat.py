"""extra context features for the 4h w1 events (s23_4h + s23_4hx): per event, from the coin's 4h bars aggregated to days
(UTC, the last CLOSED day before the event bar's day) and the bar itself; saved as s24_4h{,x}/<SYM>.npz (F2, aligned
with the w1 rows of the s23 file)"""
import sys; AV = list(sys.argv)
import os, numpy as np, warnings; warnings.filterwarnings("ignore")
os.environ["TFH"] = "4"
import s23_engine as E
FAM = E.FAMS.index("w1")
X2 = ["d_e20", "d_e50", "d_rsi", "w_ret", "d_ret3", "d_pos20", "volpct", "redrun", "b_d_e50", "b_d_ret3", "atr_ratio", "body", "vol_bar"]
def days(T, O, H, L, C):
    day = T // 86400
    st = np.flatnonzero(np.r_[True, day[1:] != day[:-1]]); en = np.r_[st[1:], len(T)]
    return day[st], np.maximum.reduceat(H, st), np.minimum.reduceat(L, st), C[en - 1]
def ctx(T, O, H, L, C, V):
    dd, dH, dL, dC = days(T, O, H, L, C)
    e20, e50 = E.ema(dC, 20), E.ema(dC, 50); r14 = E.rsi(dC, 14); datr = E.wilder(dH, dL, dC, 14)
    return dd, dH, dL, dC, e20, e50, r14, datr
_B = {}
def run(dr, sym):
    z = np.load(f"{dr}/{sym}.npz"); m = z["fam"] == FAM
    I = z["i"][m]; S = z["side"][m].astype(np.float64)
    T, O, H, L, C, V = E.load15(sym)
    if not _B:
        _B["c"] = ctx(*E.load15("BTCUSDT"))
    dd, dH, dL, dC, e20, e50, r14, datr = ctx(T, O, H, L, C, V)
    bd, _, _, bC, _, be50, _, _ = _B["c"]
    atr = E.wilder(H, L, C, 14); a100 = E.wilder(H, L, C, 100)
    F2 = np.zeros((len(I), len(X2)), np.float32)
    for k, i in enumerate(I):
        s = S[k]; day = T[i] // 86400
        j = np.searchsorted(dd, day) - 1   # the last closed day
        if j < 1: F2[k] = np.nan; continue
        a = atr[i]; px = C[i]
        F2[k, 0] = s * (px - e20[j]) / datr[j] if datr[j] > 0 else 0
        F2[k, 1] = s * (px - e50[j]) / datr[j] if datr[j] > 0 else 0
        F2[k, 2] = s * (r14[j] - 50)
        F2[k, 3] = s * (px / dC[max(j - 7, 0)] - 1) * 100
        F2[k, 4] = s * (px / dC[max(j - 3, 0)] - 1) * 100
        hi, lo = dH[max(0, j - 19):j + 1].max(), dL[max(0, j - 19):j + 1].min()
        p = (px - lo) / (hi - lo) if hi > lo else 0.5
        F2[k, 5] = p if s > 0 else 1 - p
        w = atr[max(0, i - 540):i + 1]; w = w[np.isfinite(w)]
        F2[k, 6] = (w < a).mean() if len(w) else 0.5
        r = 0
        for b in range(i, max(i - 20, 0), -1):
            if s * (C[b] - O[b]) < 0: r += 1
            else: break
        F2[k, 7] = r
        bj = np.searchsorted(bd, day) - 1
        F2[k, 8] = s * (bC[bj] / be50[bj] - 1) * 100 if bj >= 0 else 0
        F2[k, 9] = s * (bC[bj] / bC[max(bj - 3, 0)] - 1) * 100 if bj >= 0 else 0
        F2[k, 10] = a / a100[i] if a100[i] > 0 else 1
        F2[k, 11] = s * (C[i] - O[i]) / a
        F2[k, 12] = np.log((V[i] + 1e-9) / (V[max(0, i - 42):i].mean() + 1e-9))
    os.makedirs(dr.replace("s23", "s24"), exist_ok=True)
    np.savez(f"{dr.replace('s23', 's24')}/{sym}.npz", F2=F2, t=z["t"][m])
    return sym
if __name__ == "__main__":
    import multiprocessing as mp
    jobs = [("s23_4h", f[:-4]) for f in sorted(os.listdir("s23_4h"))] + [("s23_4hx", f[:-4]) for f in sorted(os.listdir("s23_4hx"))]
    with mp.Pool(2) as p:
        for k, s in enumerate(p.starmap(run, jobs)):
            pass
    print("done", len(jobs))
