"""Neuro v3 data: features every 2nd 1h bar + long / short outcomes for a grid of ATR stops, R takes, holds"""
import sys, os, time
ARGS = sys.argv[1:]
import numpy as np
from common import V, load, D
import nx_feat
import multiprocessing as mp
STOPS = (1.0, 1.5, 2.5)
TAKES = (1.0, 1.5, 2.0, 3.0)
HOLDS = (12, 48)
STEP = 2
FEE, FUND = 0.001, 0.0003
_REF = {}

def ref():
    if not _REF:
        _REF["btc"], _REF["eth"] = load("BTCUSDT"), load("ETHUSDT")
    return _REF

def funding(sym):
    fn = f"{D}/data/funding/{sym}.csv"
    if not os.path.exists(fn):
        return []
    out = []
    for l in open(fn).read().split():
        a, b = l.split(",")
        out.append((int(a), float(b)))
    return out

def labels(O, H, L, C, atr, idx):
    """outcomes per row: [side(2), stops, takes, holds] R"""
    n = len(C)
    W = max(HOLDS)
    out = np.full((len(idx), 2, len(STOPS), len(TAKES), len(HOLDS)), np.nan, dtype=np.float32)
    for r, i in enumerate(idx):
        if i + 1 + W > n or not atr[i]:
            continue
        e = O[i + 1]
        Hs, Ls, Cs = H[i + 1:i + 1 + W], L[i + 1:i + 1 + W], C[i + 1:i + 1 + W]
        for si, s in enumerate((1, -1)):
            for a_i, a in enumerate(STOPS):
                risk = a * atr[i]
                stop = e - s * risk
                hs = (Ls <= stop) if s > 0 else (Hs >= stop)
                ks = int(np.argmax(hs)) if hs.any() else -1
                for t_i, R in enumerate(TAKES):
                    tp = e + s * R * risk
                    ht = (Hs >= tp) if s > 0 else (Ls <= tp)
                    kt = int(np.argmax(ht)) if ht.any() else -1
                    for h_i, h in enumerate(HOLDS):
                        s_ = ks if 0 <= ks < h else -1
                        t_ = kt if 0 <= kt < h else -1
                        if s_ >= 0 and (t_ < 0 or s_ <= t_):
                            k, ex = s_, stop
                        elif t_ >= 0:
                            k, ex = t_, tp
                        else:
                            k, ex = h - 1, Cs[h - 1]
                        out[r, si, a_i, t_i, h_i] = s * (ex - e) / risk - (FEE + FUND * (k + 1) / 24) * e / risk
    return out

def run(sym):
    fn = f"{D}/nx/{sym}.npz"
    if os.path.exists(fn):
        return sym, -1
    t0 = time.time()
    cs = load(sym)
    if not cs or len(cs) < 24 * 60:
        return sym, 0
    R = ref()
    d1 = V._oc_agg(cs, 24)
    rows = nx_feat.nx_series(cs, V._oc_agg(cs, 4), d1, V.emw_bars(d1, "1w"), R["btc"], R["eth"], funding(sym))
    idx = [i for i in range(300, len(cs) - 1, STEP) if rows[i] is not None]
    X = np.array([rows[i] for i in idx], dtype=np.float32)
    O = np.array([c["open"] for c in cs]); H = np.array([c["high"] for c in cs]); L = np.array([c["low"] for c in cs]); C = np.array([c["close"] for c in cs])
    tr = np.maximum(H[1:] - L[1:], np.maximum(abs(H[1:] - C[:-1]), abs(L[1:] - C[:-1])))
    atr = [None] * len(cs)
    a = None
    for i in range(1, len(cs)):   # Wilder 14, as nx_feat
        if i < 14:
            continue
        a = tr[i - 14:i].mean() if a is None else (a * 13 + tr[i - 1]) / 14
        atr[i] = a
    # the same ATR as the features use (nx_feat._wilder over the full TR incl. bar 0)
    trf = nx_feat._tr([c["high"] for c in cs], [c["low"] for c in cs], [c["close"] for c in cs])
    atr = nx_feat._wilder(trf, 14)
    Y = labels(O, H, L, C, atr, idx)
    os.makedirs(f"{D}/nx", exist_ok=True)
    np.savez_compressed(fn, X=X, Y=Y, t=np.array([cs[i]["time"] for i in idx], dtype=np.int64), i=np.array(idx, dtype=np.int32))
    return sym, len(idx), round(time.time() - t0)

if __name__ == "__main__":
    syms = ARGS or sorted(f[:-4] for f in os.listdir(f"{D}/data/1h"))
    with mp.Pool(int(os.environ.get("NP", 4))) as p:
        for res in p.imap_unordered(run, syms):
            print(*res, flush=True)
