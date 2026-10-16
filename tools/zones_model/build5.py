"""entry / exit bar of the chosen rule (stop 1 day's move, take 3R) for every candidate"""
import sys, os, pickle
ARGS = sys.argv[1:]
import numpy as np
from common import load, D, V
import fastsim
import multiprocessing as mp
def run(sym):
    fn_out = f"{D}/ds5/{sym}.pkl"
    if os.path.exists(fn_out):
        return sym, -1
    rows = pickle.load(open(f"{D}/ds2/{sym}.pkl", "rb"))
    cs = load(sym)
    O = np.array([c["open"] for c in cs]); H = np.array([c["high"] for c in cs]); L = np.array([c["low"] for c in cs]); C = np.array([c["close"] for c in cs])
    out = []
    for r in rows:
        i = r["i"]; s = 1 if r["side"] == "long" else -1
        near, far = (r["hi"], r["lo"]) if s > 0 else (r["lo"], r["hi"])
        sl = slice(i, i + 336)
        x = fastsim.ladder(O[sl], H[sl], L[sl], C[sl], s, near, far, V.ZONES_LIMIT_OFF, 1.0 * r["datr"], "R", 3.0)
        out.append(None if x is None else (x[4], x[4] + x[1]))   # entry bar, exit bar (from the scan)
    os.makedirs(f"{D}/ds5", exist_ok=True)
    pickle.dump(out, open(fn_out, "wb"))
    return sym, len(out)
if __name__ == "__main__":
    syms = ARGS or [f[:-4] for f in sorted(os.listdir(f"{D}/ds2"))]
    with mp.Pool(4) as p:
        for res in p.imap_unordered(run, syms):
            pass
    import pandas as pd
    d = pd.read_parquet(f"{D}/all.parquet", columns=["sym"])
    f1, ex = [], []
    for sym in d.sym.unique():
        for x in pickle.load(open(f"{D}/ds5/{sym}.pkl", "rb")):
            f1.append(np.nan if x is None else x[0]); ex.append(np.nan if x is None else x[1])
    pd.DataFrame({"f1": np.array(f1, dtype=np.float32), "ex": np.array(ex, dtype=np.float32)}).to_parquet(f"{D}/times.parquet")
    print("ok", len(f1))
