"""the labels with the v0.99.690 exit (the take 2 ATR, back to 1 ATR after a 0.4 ATR dip, the stop 2 ATR, 32 bars) for
every event of a stream's family (the engines' npz order) -> newlab_<dir>/<sym>.npz {R}; check: with no extension (n=0)
they must equal the engine's label of the 1 / 2 / 32 exit. usage: newlabel.py DIR FAM EX TFH ENGINE ANCHOR DEPTH"""
import sys; AV = list(sys.argv)
import os, glob, importlib, numpy as np
DR, FI, EXI, TFH, ENG, ANCHOR, DEPTH = AV[1], int(AV[2]), int(AV[3]), int(AV[4]), AV[5], AV[6], float(AV[7])
os.environ["TFH"] = str(TFH); E = importlib.import_module(ENG)
from numba import njit
exec("@njit\ndef ex" + open("tkext.py").read().split("@njit\ndef ex")[1].split("\ndef run")[0])
@njit
def lab(O, H, L, C, atr, I, S, anchor_wick, depth, n, e, tfh):
    out = np.full(len(I), np.nan)
    for j in range(len(I)):
        bi = I[j]; s = S[j]; a = atr[bi]
        lv = ((L[bi] if s > 0 else H[bi]) if anchor_wick else C[bi]) - s * depth * a
        fb = -1
        for b in range(bi + 1, min(len(C), bi + 5)):
            if (s > 0 and L[b] <= lv) or (s < 0 and H[b] >= lv):
                fb = b; break
        if fb < 0: continue
        fill = min(lv, O[fb]) if s > 0 else max(lv, O[fb])
        out[j] = ex(O, H, L, C, fb, s, fill, a, n, e, 0, tfh)[0]
    return out
worst = 0.0; nn = 0; tot = 0
for d in (DR, DR + "x"):
    os.makedirs(f"newlab_{d}", exist_ok=True)
    for f in sorted(glob.glob(f"{d}/*.npz")):
        sym = os.path.basename(f)[:-4]; z = np.load(f); m = z["fam"] == FI
        if not m.any(): continue
        T, O, H, L, C, V = E.load15(sym); atr = E.wilder(H, L, C, 14)
        I = z["i"][m].astype(np.int64); S = z["side"][m].astype(np.int64)
        R = lab(O, H, L, C, atr, I, S, ANCHOR == "wick", DEPTH, 0.4, 1.0, TFH)
        R0 = lab(O, H, L, C, atr, I, S, ANCHOR == "wick", DEPTH, 0.0, 0.0, TFH)
        ok = np.isfinite(R0); dif = np.abs(R0[ok] - z["R"][EXI][m][ok]); worst = max(worst, float(dif.max()) if len(dif) else 0)
        nn += int((~np.isfinite(R)).sum()); tot += len(R)
        np.savez(f"newlab_{d}/{sym}.npz", R=R.astype(np.float32))
print(f"{DR}: events {tot}, no fill found {nn}, the old label re-made: max |diff| {worst:.5f}")
