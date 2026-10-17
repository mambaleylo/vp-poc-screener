"""Neuro: far takes (3 / 4 / 6 R) for the same rows, stops 1 / 1.5 / 2.5 ATR, holds 12 / 48 / 120 h"""
import os, sys, numpy as np
from common import load, D
import nx_feat, nx_build
import multiprocessing as mp
nx_build.TAKES = (3.0, 4.0, 6.0)
nx_build.HOLDS = (12, 48, 120)
def run(fn):
    out = fn.replace("/nx/", "/nx3/")
    if os.path.exists(out):
        return -1
    z = np.load(fn)
    sym = os.path.basename(fn)[:-4]
    cs = load(sym)
    O = np.array([c["open"] for c in cs]); H = np.array([c["high"] for c in cs]); L = np.array([c["low"] for c in cs]); C = np.array([c["close"] for c in cs])
    atr = nx_feat._wilder(nx_feat._tr(list(H), list(L), list(C)), 14)
    Y = nx_build.labels(O, H, L, C, atr, [int(i) for i in z["i"]])
    np.savez_compressed(out, Y=Y)
    return len(Y)
if __name__ == "__main__":
    import glob
    os.makedirs(f"{D}/nx3", exist_ok=True)
    with mp.Pool(int(os.environ.get("NP", 2))) as p:
        for r in p.imap_unordered(run, sorted(glob.glob(f"{D}/nx/*.npz"))):
            pass
    print("done", flush=True)
