"""Stage B: for the stage-A candidates — the new features (zfeat) and a grid of trade rules (fastsim)."""
import sys, os, pickle, time
ARGS = sys.argv[1:]
import numpy as np
from common import V, load, coins, D
import zfeat, fastsim
import multiprocessing as mp
HOLD = 14 * 24
BUFS = [("p", 1.0), ("p", 2.5), ("p", 4.0), ("d", 0.5), ("d", 1.0)]
TPS = [("pct", 3.0), ("pct", 5.0), ("pct", 8.0), ("pct", 12.0), ("pct", 20.0), ("R", 1.0), ("R", 2.0), ("R", 3.0)]
_B = {}

def btc():
    if not _B:
        b1 = load("BTCUSDT")
        _B["h1"] = b1
        _B["t"] = [c["time"] for c in b1]
        _B["d1"] = V._oc_agg(b1, 24)
        _B["dt"] = [c["time"] for c in _B["d1"]]
    return _B

def run(sym):
    fn_in, fn_out = f"{D}/ds/{sym}.pkl", f"{D}/ds2/{sym}.pkl"
    if not os.path.exists(fn_in) or os.path.exists(fn_out):
        return sym, -1
    t0 = time.time()
    rows = pickle.load(open(fn_in, "rb"))
    cs = load(sym)
    O = np.array([c["open"] for c in cs]); H = np.array([c["high"] for c in cs]); L = np.array([c["low"] for c in cs]); C = np.array([c["close"] for c in cs])
    d1_all = V._oc_agg(cs, 24)
    d_t = [c["time"] for c in d1_all]
    B = btc()
    import bisect
    by_i = {}
    for r in rows:
        by_i.setdefault(r["i"], []).append(r)
    out = []
    for i, grp in by_i.items():
        t = cs[i]["time"]
        h1 = cs[max(0, i - 480):i]
        kd = bisect.bisect_right(d_t, t - 86400)   # daily bars closed before t
        d1 = d1_all[max(0, kd - 400):kd]
        kb = bisect.bisect_left(B["t"], t)
        bh1 = B["h1"][max(0, kb - 480):kb]
        kbd = bisect.bisect_right(B["dt"], t - 86400)
        bd1 = B["d1"][max(0, kbd - 400):kbd]
        if len(d1) < 30:
            continue
        sf = zfeat.snap_feats(h1, d1, bh1, bd1)
        Of, Hf, Lf, Cf = O[i:i + HOLD], H[i:i + HOLD], L[i:i + HOLD], C[i:i + HOLD]
        for r in grp:
            cf = zfeat.cand_feats(r, h1, d1, sf, grp)
            s = 1 if r["side"] == "long" else -1
            near, far = (r["hi"], r["lo"]) if s > 0 else (r["lo"], r["hi"])
            lab = []
            for bk, bv in BUFS:
                bp = bv if bk == "p" else bv * sf["datr"]
                for tk, tv in TPS:
                    lab.append(fastsim.ladder(Of, Hf, Lf, Cf, s, near, far, V.ZONES_LIMIT_OFF, bp, tk, tv))
            out.append({"i": i, "t": t, "side": r["side"], "lo": r["lo"], "hi": r["hi"], "tf": r["tf"], "rank": r["rank"],
                        "x": r["x"], "f": cf, "datr": round(sf["datr"], 4), "lab": lab})
    os.makedirs(f"{D}/ds2", exist_ok=True)
    pickle.dump(out, open(fn_out, "wb"))
    return sym, len(out), round(time.time() - t0)

if __name__ == "__main__":
    syms = ARGS or [f[:-4] for f in sorted(os.listdir(f"{D}/ds"))]
    with mp.Pool(int(os.environ.get("NP", 4))) as p:
        for res in p.imap_unordered(run, syms):
            print(*res, flush=True)
