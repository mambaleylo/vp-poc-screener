"""P/R exit labels with a partial take (v0.99.661 night research): the deployed exits (stop by the 1h close 3 ATR, hard
6 ATR, take 4.5 ATR, 48 bars, R per the hard stop) + `part_f` of the position off at +`part_atr` ATR and the stop of the
rest moved to the entry (intrabar). ARGV: part_atr part_f out_name [take]"""
import os, sys, glob, numpy as np
ARGV = sys.argv[1:]
from numba import njit
from common import V, load, D
FEE, FUND = 0.001, 0.0003
PA, PF, OUTN = float(ARGV[0]), float(ARGV[1]), ARGV[2]
TAKE = float(ARGV[3]) if len(ARGV) > 3 else 4.5
LIM = float(ARGV[4]) if len(ARGV) > 4 else 0.0     # an entry limit this many ATR better than the next open, waiting LIMW bars
LIMW = int(ARGV[5]) if len(ARGV) > 5 else 3
SOFT, HARD = 3.0, 6.0
@njit(cache=True)
def lab(O, H, L, C, idx, sd, atr, pa, pf, take, lim, limw, out, kind, kbar):
    for j in range(len(idx)):
        i = idx[j]; s = sd[j]; a = atr[j]
        if i < 0 or i + 49 + limw > len(O) or a != a:
            out[j] = np.nan; kind[j] = -1; kbar[j] = -1; continue
        e = O[i + 1]
        if lim > 0:
            lv = O[i + 1] - s * lim * a; f = -1
            for w in range(limw):
                b = i + 1 + w
                if (s > 0 and L[b] <= lv) or (s < 0 and H[b] >= lv): f = b; break
            if f < 0:
                out[j] = np.nan; kind[j] = -1; kbar[j] = -1; continue
            e = min(lv, O[f]) if s > 0 else max(lv, O[f]); i = f - 1
        risk = HARD * a; hs = e - s * HARD * a; ss = e - s * SOFT * a; tp = e + s * take * a
        pt = e + s * pa * a; took = False
        k = 47; ex = C[i + 48]; kd = 3
        for q in range(48):
            b = i + 1 + q
            if (s > 0 and L[b] <= hs) or (s < 0 and H[b] >= hs):
                gap = took and q > 0 and ((s > 0 and O[b] <= hs) or (s < 0 and O[b] >= hs))
                k = q; ex = O[b] if gap else hs; kd = 4 if took else 0; break
            if pa > 0 and not took and ((s > 0 and H[b] >= pt) or (s < 0 and L[b] <= pt)):
                took = True; hs = e; ss = e - s * 1e9
            if (s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp):
                k = q; ex = tp; kd = 2; break
            if not took and ((s > 0 and C[b] <= ss) or (s < 0 and C[b] >= ss)):
                k = q; ex = C[b]; kd = 1; break
        fee = (e * FEE + e * FUND * (k + 1) / 24) / risk
        rest = s * (ex - e) / risk
        out[j] = ((pf * pa * a / risk + (1 - pf) * rest) if took else rest) - fee; kind[j] = kd; kbar[j] = k
res, kinds, kbars = [], [], []
for fn in sorted(glob.glob(f"{D}/prv_ev/*.npz")):
    z = np.load(fn); t = z["t"]
    if not len(t): continue
    X = z["X"]; tf = X[:, 0].astype(int); sd = X[:, 1].astype(np.int64)
    h1 = load(os.path.basename(fn)[:-4])
    o = np.full(len(t), np.nan); kk = np.full(len(t), -1, dtype=np.int64); kb = np.full(len(t), -1, dtype=np.int64)
    cs = h1
    O = np.array([c["open"] for c in cs]); H = np.array([c["high"] for c in cs]); L = np.array([c["low"] for c in cs]); C = np.array([c["close"] for c in cs])
    T = np.array([c["time"] for c in cs]); A = np.array([a if a else np.nan for a in V.neuro_atr_series(cs, 14)])
    m = np.where(tf == 1)[0]
    i = np.searchsorted(T, t[m] - 3600); i = np.where((i < len(T)) & (T[np.minimum(i, len(T) - 1)] == t[m] - 3600), i, -1)
    out = np.empty(len(m)); kd = np.empty(len(m), dtype=np.int64); kq = np.empty(len(m), dtype=np.int64)
    lab(O, H, L, C, i.astype(np.int64), sd[m], A[np.maximum(i, 0)], PA, PF, TAKE, LIM, LIMW, out, kd, kq); o[m] = out; kk[m] = kd; kb[m] = kq
    res.append(o); kinds.append(kk); kbars.append(kb)
np.savez(f"{D}/{OUTN}.npz", cs=np.concatenate(res).astype(np.float32), kind=np.concatenate(kinds).astype(np.int8), k=np.concatenate(kbars).astype(np.int16))
print("done", OUTN, flush=True)
