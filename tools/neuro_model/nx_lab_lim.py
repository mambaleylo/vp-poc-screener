"""Neuro round 4: the deployed v0.99.663 rule's label for every row of the feature store (nx/*.npz), both sides: the limit
0.3 ATR better than the next open within 3 h, stop 1 ATR, take 3R, out after 12 h; 0 when it does not fill -> nxl/<coin>.npz"""
import os, glob, numpy as np
from numba import njit
from common import load, D
import nx_feat
@njit(cache=True)
def lab(O, H, L, C, atr, idx, out):
    n = len(C)
    for z in range(len(idx)):
        i = idx[z]; a = atr[i]
        for si in range(2):
            s = 1 if si == 0 else -1
            if a != a or i + 16 >= n: out[z, si] = np.nan; continue
            lv = O[i + 1] - s * 0.3 * a; f = -1
            for q in range(3):
                b = i + 1 + q
                if (s > 0 and L[b] <= lv) or (s < 0 and H[b] >= lv): f = b; break
            if f < 0: out[z, si] = 0.0; continue
            e = min(lv, O[f]) if s > 0 else max(lv, O[f]); st = e - s * a; tp = e + s * 3 * a
            k = 11; ex = C[f + 11]
            for q in range(12):
                b = f + q
                if (s > 0 and L[b] <= st) or (s < 0 and H[b] >= st):
                    gap = q > 0 and ((s > 0 and O[b] <= st) or (s < 0 and O[b] >= st)); ex = O[b] if gap else st; k = q; break
                if (s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp): ex = tp; k = q; break
            out[z, si] = (s * (ex - e) - (0.001 + 0.0003 * (k + 1) / 24) * e) / a
os.makedirs(f"{D}/nxl", exist_ok=True)
for fn in sorted(glob.glob(f"{D}/nx/*.npz")):
    z = np.load(fn); sym = os.path.basename(fn)[:-4]
    if not len(z["t"]): np.savez(f"{D}/nxl/{sym}.npz", Y=np.zeros((0, 2))); continue
    cs = load(sym)
    O = np.array([c["open"] for c in cs]); H = np.array([c["high"] for c in cs]); L = np.array([c["low"] for c in cs]); C = np.array([c["close"] for c in cs])
    atr = np.array([a if a is not None else np.nan for a in nx_feat._wilder(nx_feat._tr(list(H), list(L), list(C)), 14)])
    out = np.empty((len(z["i"]), 2)); lab(O, H, L, C, atr, z["i"].astype(np.int64), out)
    np.savez(f"{D}/nxl/{sym}.npz", Y=out)
print("done", flush=True)
