"""H17 step 2 — the model's events (the user: "Пробуй" after the plain rule lost on every variant): every 1h close beyond the
Bollinger band (20, 2 sd) inside a calm, narrow range (the band's width in the lower half of its last 30 days, the efficiency ratio
of 48 h < 0.25) -> against it at the next open. Its features: the range's own (side, the depth beyond the band in sd, the width's
rank, ER, the hours calm, ATR %, the candle's body / wick, the band's slope, the distance of the middle in ATR) + the Neuro context
of the 1h bar (nx_feat, the same 89 the bot computes for P/R); its outcomes R for each stop (1, 1.5, 2 ATR) x take (0.75, 1, 1.5
ATR, the middle), out after 24 h; 0.10% round trip and the funding. -> <LABSTORE>/h17_ev/<SYM>.npz. usage: h17_ev.py [coins…]"""
import sys, os, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "..", "prv_audit"), os.path.join(HERE, "..", "neuro_model"), os.path.join(HERE, "..", "winrate")]
import numpy as np, pandas as pd
import prv_ev2   # the lab-store's candles as common.load
from common import V, load, D
import nx_feat
from nx_build import funding
import multiprocessing as mp
STOPS = (1.0, 1.5, 2.0)
TAKES = (0.75, 1.0, 1.5, "mid")
HOLD = 24
FEE, FUND = 0.001, 0.0003
T0 = 1609459200   # 2021-01-01: the first year the walk-forward trains on
NAMES = ["side", "depth", "w_rank", "er48", "calm_n", "atrp", "body", "wick", "slope", "mid_atr", "bw"]
_REF = {}


def ref():
    if not _REF:
        _REF["btc"], _REF["eth"] = load("BTCUSDT"), load("ETHUSDT")
    return _REF


def run(sym):
    fn = f"{D}/h17_ev/{sym}.npz"
    if os.path.exists(fn):
        return sym, -1
    t0 = time.time()
    h1 = load(sym)
    if not h1 or len(h1) < 24 * 90:
        return sym, 0
    R_ = ref()
    h4 = V._oc_agg(h1, 4); d1 = V._oc_agg(h1, 24)
    rows = nx_feat.nx_series(h1, h4, d1, V.emw_bars(d1, "1w"), R_["btc"], R_["eth"], funding(sym))
    O = np.array([c["open"] for c in h1]); H = np.array([c["high"] for c in h1]); L = np.array([c["low"] for c in h1]); C = np.array([c["close"] for c in h1])
    T = np.array([c["time"] for c in h1]); n = len(C)
    pc = np.r_[C[0], C[:-1]]; tr = np.maximum(H - L, np.maximum(abs(H - pc), abs(L - pc)))
    atr = pd.Series(tr).rolling(14).mean().values
    mid = pd.Series(C).rolling(20).mean().values; sd = pd.Series(C).rolling(20).std(ddof=0).values
    bw_s = pd.Series(4 * sd / mid); bw = bw_s.values
    w_rank = bw_s.rolling(720).rank(pct=True).values
    er = (pd.Series(C).diff(48).abs() / pd.Series(C).diff().abs().rolling(48).sum()).values
    calm = (w_rank <= 0.5) & (er < 0.25)
    calm_n = np.zeros(n)
    for i in range(1, n):
        calm_n[i] = calm_n[i - 1] + 1 if calm[i] else 0
    Xs, Ys, Ts = [], [], []
    for i in range(800, n - 1):
        if T[i] < T0 or not calm[i] or not np.isfinite(atr[i]) or atr[i] <= 0 or rows[i] is None:
            continue
        z = (C[i] - mid[i]) / sd[i] if sd[i] > 0 else 0
        if abs(z) < 2:
            continue
        s = -1 if z > 0 else 1; a = atr[i]; e = O[i + 1]; rg = H[i] - L[i]
        f = [float(s), abs(z), w_rank[i], er[i], calm_n[i], a / C[i] * 100, -s * (C[i] - O[i]) / rg if rg > 0 else 0.0,
             ((min(O[i], C[i]) - L[i]) if s > 0 else (H[i] - max(O[i], C[i]))) / rg if rg > 0 else 0.0,
             -s * (mid[i] - mid[i - 5]) / a, s * (mid[i] - e) / a, bw[i]]
        y = np.full((len(STOPS), len(TAKES)), np.nan, dtype=np.float32)
        w_end = i + 1 + HOLD
        if w_end <= n:
            Hs, Ls, Cs = H[i + 1:w_end], L[i + 1:w_end], C[i + 1:w_end]
            for si, sk in enumerate(STOPS):
                stop = e - s * sk * a; risk = sk * a
                hs = (Ls <= stop) if s > 0 else (Hs >= stop)
                ks = int(np.argmax(hs)) if hs.any() else 10 ** 6
                for ti, tk in enumerate(TAKES):
                    tp = mid[i] if tk == "mid" else e + s * tk * a
                    if (tp - e) * s <= 0.2 * a:
                        continue
                    ht = (Hs >= tp) if s > 0 else (Ls <= tp)
                    kt = int(np.argmax(ht)) if ht.any() else 10 ** 6
                    if ks <= kt and ks < HOLD:
                        k, ex = ks, stop
                    elif kt < HOLD:
                        k, ex = kt, tp
                    else:
                        k, ex = HOLD - 1, Cs[-1]
                    y[si, ti] = (s * (ex - e) - e * FEE - e * FUND * (k + 1) / 24) / risk
        Xs.append(f + rows[i]); Ys.append(y); Ts.append(int(T[i] + 3600))
    os.makedirs(f"{D}/h17_ev", exist_ok=True)
    np.savez_compressed(fn, X=np.array(Xs, dtype=np.float32), Y=np.array(Ys, dtype=np.float32), t=np.array(Ts, dtype=np.int64))
    return sym, len(Ts), round(time.time() - t0)


if __name__ == "__main__":
    import json
    sp = json.load(open(os.path.join(HERE, "..", "winrate", "lv", "split.json")))
    syms = sys.argv[1:] or sorted(set(sp["bot"]) | set(sp["chk"]))
    with mp.Pool(int(os.environ.get("NP", 4))) as p:
        for res in p.imap_unordered(run, syms):
            print(*res, flush=True)
    print("h17 ev done", flush=True)
