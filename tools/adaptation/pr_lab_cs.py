"""P/R exit label with the stop by CLOSE (v0.99.641), aligned with prv_wf's event order: soft stop 3 ATR checked on the
close of the trade's own bar (1h / 4h), a hard stop 6 ATR (intrabar), take 4.5 ATR, 48 bars. R per the hard stop's
distance (the sizing risk). In one bar: hard stop first, then take, then the close beyond the soft stop."""
import os, sys, glob, numpy as np
ARGV = sys.argv[1:]
from numba import njit
from common import V, load, D
FEE, FUND = 0.001, 0.0003
SOFT, HARD, TAKE = (float(ARGV[0]), float(ARGV[1]), float(ARGV[2])) if ARGV else (3.0, 6.0, 4.5)
OUTN = ARGV[3] if len(ARGV) > 3 else "prv_lab_cs"
@njit(cache=True)
def lab(O, H, L, C, idx, sd, atr, soft, hard, take, hrs, out, kind, kbar):
    for j in range(len(idx)):
        i = idx[j]; s = sd[j]; a = atr[j]
        if i < 0 or i + 49 > len(O) or a != a:
            out[j] = np.nan; kind[j] = -1; kbar[j] = -1; continue
        e = O[i + 1]; risk = hard * a; hs = e - s * hard * a; ss = e - s * soft * a; tp = e + s * take * a
        k = 47; ex = C[i + 48]; kd = 3
        for q in range(48):
            b = i + 1 + q
            if (s > 0 and L[b] <= hs) or (s < 0 and H[b] >= hs):
                k = q; ex = hs; kd = 0; break
            if (s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp):
                k = q; ex = tp; kd = 2; break
            if (s > 0 and C[b] <= ss) or (s < 0 and C[b] >= ss):
                k = q; ex = C[b]; kd = 1; break
        out[j] = (s * (ex - e) - e * FEE - e * FUND * (k + 1) * hrs / 24) / risk; kind[j] = kd; kbar[j] = k
res, kinds, kbars = [], [], []
for fn in sorted(glob.glob(f"{D}/prv_ev/*.npz")):
    z = np.load(fn); t = z["t"]
    if not len(t): continue
    X = z["X"]; tf = X[:, 0].astype(int); sd = X[:, 1].astype(np.int64)
    h1 = load(os.path.basename(fn)[:-4])
    o = np.full(len(t), np.nan); kk = np.full(len(t), -1, dtype=np.int64); kb = np.full(len(t), -1, dtype=np.int64)
    for hrs in (1, 4):
        cs = h1 if hrs == 1 else V._oc_agg(h1, 4)
        O = np.array([c["open"] for c in cs]); H = np.array([c["high"] for c in cs]); L = np.array([c["low"] for c in cs]); C = np.array([c["close"] for c in cs])
        T = np.array([c["time"] for c in cs]); A = np.array([a if a else np.nan for a in V.neuro_atr_series(cs, 14)])
        m = np.where(tf == hrs)[0]
        i = np.searchsorted(T, t[m] - hrs * 3600); i = np.where((i < len(T)) & (T[np.minimum(i, len(T) - 1)] == t[m] - hrs * 3600), i, -1)
        out = np.empty(len(m)); kd = np.empty(len(m), dtype=np.int64); kq = np.empty(len(m), dtype=np.int64)
        lab(O, H, L, C, i.astype(np.int64), sd[m], A[np.maximum(i, 0)], SOFT, HARD, TAKE, hrs, out, kd, kq); o[m] = out; kk[m] = kd; kb[m] = kq
    res.append(o); kinds.append(kk); kbars.append(kb)
np.savez(f"{D}/{OUTN}.npz", cs=np.concatenate(res).astype(np.float32), kind=np.concatenate(kinds).astype(np.int8), k=np.concatenate(kbars).astype(np.int16))
print("done", flush=True)
