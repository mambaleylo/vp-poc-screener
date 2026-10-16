"""Confirmation-entry labels for the stage-A candidates."""
import sys, os, pickle, time
ARGS = sys.argv[1:]
import numpy as np
from common import load, D
from confsim import conf
import multiprocessing as mp
WAIT = 14 * 24
KS = [1.0, 1.5, 2.0, 3.0, 5.0]
MODES = [("rej", 24, 0.3, 168), ("rejt", 24, 0.3, 168), ("sweep", 12, 0.3, 168), ("rej", 24, 0.3, 336)]

def run(sym):
    fn_in, fn_out = f"{D}/ds/{sym}.pkl", f"{D}/ds3/{sym}.pkl"
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
        seg = slice(i, i + WAIT + 336)
        labs = []
        for mode, W, buf, hold in MODES:
            labs.append(conf(O[seg], H[seg], L[seg], C[seg], s, r["lo"], r["hi"], mode, W, buf, KS, hold, wait=WAIT))
        out.append(labs)
    os.makedirs(f"{D}/ds3", exist_ok=True)
    pickle.dump(out, open(fn_out, "wb"))
    return sym, len(out), round(time.time() - t0)

if __name__ == "__main__":
    syms = ARGS or [f[:-4] for f in sorted(os.listdir(f"{D}/ds"))]
    with mp.Pool(int(os.environ.get("NP", 4))) as p:
        for res in p.imap_unordered(run, syms):
            print(*res, flush=True)
