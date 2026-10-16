"""More rule variants around the best one (volatility stop, take in R)."""
import sys, os, pickle, time
ARGS = sys.argv[1:]
import numpy as np
from common import load, D, V
import fastsim
import multiprocessing as mp
HOLD = 14 * 24
GRID = [(b, t) for b in (0.75, 1.0, 1.5, 2.0) for t in (("R", 1.5), ("R", 2.0), ("R", 3.0), ("R", 4.0), ("R", 6.0), ("pct", 30.0))]

def run(sym):
    fn_in, fn_out = f"{D}/ds2/{sym}.pkl", f"{D}/ds4/{sym}.pkl"
    if not os.path.exists(fn_in) or os.path.exists(fn_out):
        return sym, -1
    t0 = time.time()
    rows = pickle.load(open(fn_in, "rb"))
    cs = load(sym)
    O = np.array([c["open"] for c in cs]); H = np.array([c["high"] for c in cs]); L = np.array([c["low"] for c in cs]); C = np.array([c["close"] for c in cs])
    out = []
    for r in rows:
        i = r["i"]
        s = 1 if r["side"] == "long" else -1
        near, far = (r["hi"], r["lo"]) if s > 0 else (r["lo"], r["hi"])
        sl = slice(i, i + HOLD)
        out.append([fastsim.ladder(O[sl], H[sl], L[sl], C[sl], s, near, far, V.ZONES_LIMIT_OFF, b * r["datr"], tk, tv) for b, (tk, tv) in GRID])
    os.makedirs(f"{D}/ds4", exist_ok=True)
    pickle.dump(out, open(fn_out, "wb"))
    return sym, len(out), round(time.time() - t0)

if __name__ == "__main__":
    syms = ARGS or [f[:-4] for f in sorted(os.listdir(f"{D}/ds2"))]
    with mp.Pool(int(os.environ.get("NP", 2))) as p:
        for res in p.imap_unordered(run, syms):
            print(*res, flush=True)
