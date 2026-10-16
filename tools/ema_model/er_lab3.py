"""far takes on the same EMA touches: stop 0.5 / 0.75 / 1 daily ATR, take 4 / 5 / 6 / 8 R, hold 1 / 3 / 7 days"""
import os, pickle, numpy as np, pandas as pd
import er_lab2 as L2
from common import load, D
import multiprocessing as mp
L2.STOPS2 = (0.5, 0.75, 1.0)
L2.TAKES2 = (4.0, 5.0, 6.0, 8.0)
L2.HOLDS2 = (1, 3, 7)
NAMES3 = [f"F_{a}_{R}_{h}" for a in L2.STOPS2 for R in L2.TAKES2 for h in L2.HOLDS2]
def run(sym):
    fn = f"{D}/er3/{sym}.pkl"
    if os.path.exists(fn):
        return sym, -1
    rows = pickle.load(open(f"{D}/er/{sym}.pkl", "rb"))
    if not rows:
        pickle.dump(np.zeros((0, len(NAMES3), 2), dtype=np.float32), open(fn, "wb"))
        return sym, 0
    cs = load(sym)
    O = np.array([c["open"] for c in cs]); H = np.array([c["high"] for c in cs]); L = np.array([c["low"] for c in cs]); C = np.array([c["close"] for c in cs])
    arr = np.zeros((len(rows), len(NAMES3), 2), dtype=np.float32)
    for i, r in enumerate(rows):
        arr[i] = np.array(L2.lab_one(O, H, L, C, r["j"], r["side"], r["lv"], r["f"]["datr"]), dtype=np.float32)
    pickle.dump(arr, open(fn, "wb"))
    return sym, len(rows)
if __name__ == "__main__":
    os.makedirs(f"{D}/er3", exist_ok=True)
    syms = sorted(f[:-4] for f in os.listdir(f"{D}/er"))
    with mp.Pool(2) as p:
        for res in p.imap_unordered(run, syms):
            pass
    d = pd.read_parquet(f"{D}/er_all.parquet")
    A = np.concatenate([pickle.load(open(f"{D}/er3/{sym}.pkl", "rb")) for sym in d.sym.unique()])
    assert len(A) == len(d), (len(A), len(d))
    new = {}
    for k, nm in enumerate(NAMES3):
        new[nm] = A[:, k, 0].astype(np.float32)
        new[nm + "_h"] = A[:, k, 1].astype(np.int16)
    d = pd.concat([d, pd.DataFrame(new)], axis=1)
    d.to_parquet(f"{D}/er_all.parquet")
    print(d.shape, flush=True)
