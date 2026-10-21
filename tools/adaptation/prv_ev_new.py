"""v0.99.670: the same events for the extra coins (new_coins.txt) -> prv_ev_new/. Was: Peak Reversal audit, part 2: every band event (EMA20 Keltner, 1h and 4h) with its band features + the Neuro
context of the 1h bar closing with it, and its outcomes (stop x take, 48 bars) — for filters and a model"""
import sys, os, time
ARGS = sys.argv[1:]
import numpy as np
from common import V, load, D
import nx_feat
from nx_build import funding
import multiprocessing as mp
STOPS = (1.0, 1.5, "ext")
TAKES = (1.0, 1.5, 2.0, 3.0, "mid")
HOLD = 48
FEE, FUND = 0.001, 0.0003
BAND_NAMES = ["tf", "side", "depth", "cdepth", "pdepth", "outside_n", "reent", "close_out", "slope", "squeeze", "atrp", "body", "wick"]
_REF = {}
def ref():
    if not _REF:
        _REF["btc"], _REF["eth"] = load("BTCUSDT"), load("ETHUSDT")
    return _REF

def run(sym):
    fn = f"{D}/prv_ev_new/{sym}.npz"
    if os.path.exists(fn):
        return sym, -1
    t0 = time.time()
    h1 = load(sym)
    if not h1 or len(h1) < 24 * 60:
        return sym, 0
    R_ = ref()
    h4 = V._oc_agg(h1, 4); d1 = V._oc_agg(h1, 24)
    rows = nx_feat.nx_series(h1, h4, d1, V.emw_bars(d1, "1w"), R_["btc"], R_["eth"], funding(sym))
    h1_end = np.array([c["time"] + 3600 for c in h1])
    Xs, Ys, Ts = [], [], []
    for tf, hrs, cs in (("1h", 1, h1), ("4h", 4, h4)):
        n = len(cs)
        O = np.array([c["open"] for c in cs]); H = np.array([c["high"] for c in cs]); L = np.array([c["low"] for c in cs]); C = np.array([c["close"] for c in cs])
        T = np.array([c["time"] for c in cs])
        atr = np.array([a if a else np.nan for a in V.neuro_atr_series(cs, 14)])
        bs = np.array([b if b is not None else np.nan for b in V.prv_ma_series(cs, "EMA", 20)])
        sd = np.array([np.std(C[max(0, i - 19):i + 1]) if i >= 19 else np.nan for i in range(n)])
        hi_d, lo_d, c_d = (H - bs) / atr, (bs - L) / atr, (C - bs) / atr
        out_n = np.zeros(n)
        for i in range(1, n):
            out_n[i] = out_n[i - 1] + 1 if abs(c_d[i]) >= 1.5 else 0
        for i in range(40, n - 1):
            if np.isnan(atr[i]) or np.isnan(bs[i]):
                continue
            ev = []
            if hi_d[i] >= 1.5 or (c_d[i - 1] >= 1.5 and c_d[i] < c_d[i - 1]):
                ev.append(-1)
            if lo_d[i] >= 1.5 or (c_d[i - 1] <= -1.5 and c_d[i] > c_d[i - 1]):
                ev.append(1)
            if len(ev) != 1:
                continue
            s = ev[0]
            k1 = np.searchsorted(h1_end, T[i] + hrs * 3600, side="right") - 1
            if k1 < 0 or rows[k1] is None:
                continue
            a = atr[i]; e = O[i + 1]
            depth = hi_d[i] if s < 0 else lo_d[i]
            cdepth = -s * c_d[i]; pdepth = -s * c_d[i - 1]
            rg = H[i] - L[i]
            f = [float(hrs), float(s), depth, cdepth, pdepth, out_n[i], float(pdepth >= 1.5 and cdepth < pdepth), float(cdepth >= 1.5),
                 s * (bs[i] - bs[i - 5]) / a, (2 * sd[i]) / (1.5 * a) if a else 1.0, a / C[i] * 100,
                 s * (C[i] - O[i]) / rg if rg > 0 else 0.0, ((min(O[i], C[i]) - L[i]) if s > 0 else (H[i] - max(O[i], C[i]))) / rg if rg > 0 else 0.0]
            y = np.full((len(STOPS), len(TAKES)), np.nan, dtype=np.float32)
            w_end = i + 1 + HOLD
            if w_end <= n:
                Hs, Ls, Cs = H[i + 1:w_end], L[i + 1:w_end], C[i + 1:w_end]
                for si, sk in enumerate(STOPS):
                    stop = (H[i] if s < 0 else L[i]) - s * 0.2 * a if sk == "ext" else e - s * sk * a
                    risk = (e - stop) * s
                    if risk <= e * 0.001:
                        continue
                    hs = (Ls <= stop) if s > 0 else (Hs >= stop)
                    ks = int(np.argmax(hs)) if hs.any() else 10 ** 6
                    for ti, tk in enumerate(TAKES):
                        tp = bs[i] if tk == "mid" else e + s * tk * risk
                        if (tp - e) * s <= 0:
                            continue
                        ht = (Hs >= tp) if s > 0 else (Ls <= tp)
                        kt = int(np.argmax(ht)) if ht.any() else 10 ** 6
                        if ks <= kt and ks < HOLD:
                            k, ex = ks, stop
                        elif kt < HOLD:
                            k, ex = kt, tp
                        else:
                            k, ex = HOLD - 1, Cs[-1]
                        y[si, ti] = (s * (ex - e) - e * FEE - e * FUND * (k + 1) * hrs / 24) / risk
            Xs.append(f + rows[k1]); Ys.append(y); Ts.append(int(T[i] + hrs * 3600))
    os.makedirs(f"{D}/prv_ev_new", exist_ok=True)
    np.savez_compressed(fn, X=np.array(Xs, dtype=np.float32), Y=np.array(Ys, dtype=np.float32), t=np.array(Ts, dtype=np.int64))
    return sym, len(Ts), round(time.time() - t0)

if __name__ == "__main__":
    syms = ARGS or open(f"{D}/new_coins.txt").read().split()
    with mp.Pool(int(os.environ.get("NP", 3))) as p:
        for res in p.imap_unordered(run, syms):
            print(*res, flush=True)
