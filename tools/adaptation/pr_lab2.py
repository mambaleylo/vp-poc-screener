"""Extra P/R labels aligned with prv_wf's event order: stop 1.0 ATR / take 4.5 ATR (the base take's place), and the
base 1.5 / 3R recomputed as a check against prv_ev's own label. Bar-level, 48 bars, stop first when one bar hits both."""
import os, sys, glob, numpy as np
ARGV = sys.argv[:]
from numba import njit
from common import V, load, D
FEE, FUND = 0.001, 0.0003
@njit(cache=True)
def lab(O, H, L, C, idx, sd, atr, ks, kt, hrs, out):
    for j in range(len(idx)):
        i = idx[j]; s = sd[j]; a = atr[j]
        if i < 0 or i + 49 > len(O) or a != a:
            out[j] = np.nan; continue
        e = O[i + 1]; risk = ks * a; stop = e - s * risk; tp = e + s * kt * a
        k = 47; ex = C[i + 48]
        for q in range(48):
            b = i + 1 + q
            if (s > 0 and L[b] <= stop) or (s < 0 and H[b] >= stop):
                k = q; ex = stop; break
            if (s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp):
                k = q; ex = tp; break
        out[j] = (s * (ex - e) - e * FEE - e * FUND * (k + 1) * hrs / 24) / risk
import sys
SETS = {a: (float(a[1:3]) / 10, float(a.split("_t")[1]) / 10) for a in ARGV[2:]} if len(ARGV) > 2 else {"s10_t45": (1.0, 4.5), "s15_t45": (1.5, 4.5)}
OUTF = ARGV[1] if len(ARGV) > 1 else "prv_lab2"
res = {k: [] for k in SETS}
for fn in sorted(glob.glob(f"{D}/prv_ev/*.npz")):
    z = np.load(fn); t = z["t"]
    if not len(t): continue
    X = z["X"]; tf = X[:, 0].astype(int); sd = X[:, 1].astype(np.int64)
    h1 = load(os.path.basename(fn)[:-4])
    o = {k: np.full(len(t), np.nan) for k in SETS}
    for hrs in (1, 4):
        cs = h1 if hrs == 1 else V._oc_agg(h1, 4)
        O = np.array([c["open"] for c in cs]); H = np.array([c["high"] for c in cs]); L = np.array([c["low"] for c in cs]); C = np.array([c["close"] for c in cs])
        T = np.array([c["time"] for c in cs]); A = np.array([a if a else np.nan for a in V.neuro_atr_series(cs, 14)])
        m = np.where(tf == hrs)[0]
        i = np.searchsorted(T, t[m] - hrs * 3600); i = np.where((i < len(T)) & (T[np.minimum(i, len(T) - 1)] == t[m] - hrs * 3600), i, -1)
        for k, (ks, kt) in SETS.items():
            out = np.empty(len(m)); lab(O, H, L, C, i.astype(np.int64), sd[m], A[np.maximum(i, 0)], ks, kt, hrs, out); o[k][m] = out
    for k in SETS: res[k].append(o[k])
    print(os.path.basename(fn), len(t), flush=True)
np.savez(f"{D}/{OUTF}.npz", **{k: np.concatenate(v).astype(np.float32) for k, v in res.items()})
