"""a finer grid of short trades on the same touches"""
import sys, os, pickle, numpy as np, pandas as pd
from common import load, D
import multiprocessing as mp
STOPS2 = (0.25, 0.5, 0.75, 1.0)
TAKES2 = (1.0, 1.5, 2.0, 3.0)
HOLDS2 = (1, 2, 3, 7)
FEE, FUND = 0.001, 0.0003
NAMES2 = [f"F_{a}_{R}_{h}" for a in STOPS2 for R in TAKES2 for h in HOLDS2]

def lab_one(O, H, L, C, j, side, fill, datr):
    out = []
    n = len(C)
    e = min(n, j + 24 * max(HOLDS2))
    Hs, Ls = H[j:e], L[j:e]
    for a in STOPS2:
        risk = fill * a * datr / 100
        stop = fill - side * risk
        hit_s = (Ls <= stop) if side > 0 else (Hs >= stop)
        ks = int(np.argmax(hit_s)) if hit_s.any() else -1
        for R in TAKES2:
            tp = fill + side * R * risk
            hit_t = (Hs >= tp) if side > 0 else (Ls <= tp)
            hit_t[0] = False
            kt = int(np.argmax(hit_t)) if hit_t.any() else -1
            for h in HOLDS2:
                lim = min(len(Hs), 24 * h)
                s_ = ks if 0 <= ks < lim else -1
                t_ = kt if 0 <= kt < lim else -1
                if s_ >= 0 and (t_ < 0 or s_ <= t_):
                    k = s_
                    gap = (O[j + k] <= stop) if side > 0 else (O[j + k] >= stop)
                    ex = O[j + k] if (gap and k > 0) else stop
                elif t_ >= 0:
                    k, ex = t_, tp
                else:
                    k = lim - 1
                    ex = C[j + k]
                r = side * (ex - fill) / risk - (FEE + FUND * (k + 1) / 24) * fill / risk
                out.append((r, k + 1))
    return out

def run(sym):
    fn = f"{D}/er2/{sym}.pkl"
    if os.path.exists(fn):
        return sym, -1
    rows = pickle.load(open(f"{D}/er/{sym}.pkl", "rb"))
    if not rows:
        pickle.dump(np.zeros((0, len(NAMES2), 2), dtype=np.float32), open(fn, "wb"))
        return sym, 0
    cs = load(sym)
    O = np.array([c["open"] for c in cs]); H = np.array([c["high"] for c in cs]); L = np.array([c["low"] for c in cs]); C = np.array([c["close"] for c in cs])
    arr = np.zeros((len(rows), len(NAMES2), 2), dtype=np.float32)
    for i, r in enumerate(rows):
        arr[i] = np.array(lab_one(O, H, L, C, r["j"], r["side"], r["lv"], r["f"]["datr"]), dtype=np.float32)
    pickle.dump(arr, open(fn, "wb"))
    return sym, len(rows)

if __name__ == "__main__":
    os.makedirs(f"{D}/er2", exist_ok=True)
    syms = sorted(f[:-4] for f in os.listdir(f"{D}/er"))
    with mp.Pool(3) as p:
        for res in p.imap_unordered(run, syms):
            pass
    d = pd.read_parquet(f"{D}/er_all.parquet")
    arrs = []
    for sym in d.sym.unique():
        arrs.append(pickle.load(open(f"{D}/er2/{sym}.pkl", "rb")))
    A = np.concatenate(arrs)
    assert len(A) == len(d), (len(A), len(d))
    new = {}
    for k, nm in enumerate(NAMES2):
        new[nm] = A[:, k, 0].astype(np.float32)
        new[nm + "_h"] = A[:, k, 1].astype(np.int16)
    d = pd.concat([d, pd.DataFrame(new)], axis=1)
    d.to_parquet(f"{D}/er_all.parquet")
    print(d.shape)
