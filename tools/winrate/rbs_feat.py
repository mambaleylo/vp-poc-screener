"""the short breakout's features (for a model picking the best of rb_short.py's events), each signed by the trade's side
where it has a side: the breakout bar (strength, body, range, volume), the squeeze (range / ATR100, ATR / ATR100), the
trend (EMA50 / 200 distance and slope, returns 1..48 bars, the place in the 100-bar range), RSI, BTC's (returns,
EMA200, ATR %), the hour and the weekday. All from the closed bars up to the signal's close.
usage: rbs_feat.py TFH -> <LABSTORE>/wf/rbs_<tf>_X.npz (rows aligned with rbs_<tf>.npz)"""
import sys, os, gzip, numpy as np
from multiprocessing import Pool
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
TFH = int(sys.argv[1]) if len(sys.argv) > 1 else 4
NAMES = ["side", "N", "rg", "brk", "body", "bar_atr", "atr_pct", "atr_x", "vol_x", "vol_x5", "d_e50", "d_e200", "sl_e200", "sl_e50",
         "r1", "r3", "r6", "r12", "r24", "r48", "pos100", "rsi", "up_run", "b_r6", "b_r24", "b_r72", "b_e200", "b_atr", "b_rel24",
         "hour", "wday"]


def load(sym):
    a = np.loadtxt(gzip.open(f"{ST}/data/1h/{sym}.csv.gz", "rt"), delimiter=",", usecols=(0, 1, 2, 3, 4, 5))
    if TFH == 1:
        return [a[:, k] for k in range(6)]
    g = (a[:, 0] // (TFH * 3600)).astype(np.int64)
    cut = np.flatnonzero(np.diff(g)) + 1
    st = np.r_[0, cut]; en = np.r_[cut, len(a)]; full = (en - st) == TFH
    H = np.maximum.reduceat(a[:, 2], st)[full]; L = np.minimum.reduceat(a[:, 3], st)[full]; Vv = np.add.reduceat(a[:, 5], st)[full]
    st, en = st[full], en[full]
    return [(g[st] * TFH * 3600).astype(float), a[st, 1], H, L, a[en - 1, 4], Vv]


def ema(x, n):
    o = np.empty(len(x)); k = 2 / (n + 1); e = x[0]
    for i, v in enumerate(x):
        e = e + k * (v - e); o[i] = e
    return o


def wilder(x, n):
    o = np.full(len(x), np.nan)
    if len(x) < n: return o
    v = x[:n].mean(); o[n - 1] = v
    for i in range(n, len(x)):
        v = (v * (n - 1) + x[i]) / n; o[i] = v
    return o


def sma(x, n):
    o = np.convolve(x, np.ones(n) / n, "full")[:len(x)]; o[:n - 1] = np.nan; return o


def lag(x, k):
    return np.r_[np.full(k, np.nan), x[:-k]]


def base(T, O, H, L, C, Vv):
    tr = np.r_[H[0] - L[0], np.maximum(H[1:], C[:-1]) - np.minimum(L[1:], C[:-1])]
    atr = wilder(tr, 14); a100 = sma(tr, 100)
    e50, e200 = ema(C, 50), ema(C, 200)
    d = np.diff(C, prepend=C[0]); up = wilder(np.maximum(d, 0), 14); dn = wilder(np.maximum(-d, 0), 14)
    rsi = 100 - 100 / (1 + up / np.maximum(dn, 1e-12))
    from numpy.lib.stride_tricks import sliding_window_view as sw
    hh = np.full(len(C), np.nan); ll = np.full(len(C), np.nan); hh[99:] = sw(H, 100).max(1); ll[99:] = sw(L, 100).min(1)
    return {"atr": atr, "a100": a100, "e50": e50, "e200": e200, "rsi": rsi, "hh": hh, "ll": ll, "vs": sma(Vv, 20), "vs5": sma(Vv, 5)}


_BTC = {}


def btc():
    if not _BTC:
        T, O, H, L, C, Vv = load("BTCUSDT"); b = base(T, O, H, L, C, Vv)
        _BTC.update(T=T + TFH * 3600, C=C, e200=b["e200"], atr=b["atr"])
    return _BTC


def run(sym_rows):
    sym, rows = sym_rows
    T, O, H, L, C, Vv = load(sym); b = base(T, O, H, L, C, Vv); Te = T + TFH * 3600
    B = btc(); bi = np.searchsorted(B["T"], Te, side="right") - 1   # BTC's last bar closed by then
    out = np.full((len(rows), len(NAMES)), np.nan, np.float32)
    k6, k24, k72 = (max(1, int(h / TFH)) for h in (6, 24, 72))
    for j, (t, s, N, rg, brk) in enumerate(rows):
        i = int(np.searchsorted(Te, t))
        if i >= len(Te) or Te[i] != t or i < 60:
            continue
        a = b["atr"][i]; bj = bi[i]
        r = lambda k: s * (C[i] / C[i - k] - 1) / (a / C[i]) if i >= k else np.nan
        br = lambda k: (B["C"][bj] / B["C"][bj - k] - 1) * 100 * s if bj >= k else np.nan
        # how many of the last 10 bars closed in the trade's direction
        run_ = float(np.sum(s * np.sign(C[i - 9:i + 1] - O[i - 9:i + 1]) > 0))
        out[j] = [s, N, rg, brk, s * (C[i] - O[i]) / max(H[i] - L[i], 1e-12), (H[i] - L[i]) / a, a / C[i] * 100, a / b["a100"][i],
                  Vv[i] / max(b["vs"][i - 1], 1e-12), b["vs5"][i] / max(b["vs"][i - 5], 1e-12),
                  s * (C[i] - b["e50"][i]) / a, s * (C[i] - b["e200"][i]) / a, s * (b["e200"][i] - b["e200"][i - 20]) / a, s * (b["e50"][i] - b["e50"][i - 10]) / a,
                  r(1), r(3), r(6), r(12), r(24), r(48),
                  ((C[i] - b["ll"][i]) / max(b["hh"][i] - b["ll"][i], 1e-12)) if s > 0 else ((b["hh"][i] - C[i]) / max(b["hh"][i] - b["ll"][i], 1e-12)),
                  (b["rsi"][i] - 50) * s, run_, br(k6), br(k24), br(k72), s * np.sign(B["C"][bj] - B["e200"][bj]), B["atr"][bj] / B["C"][bj] * 100,
                  r(k24) - br(k24) / (a / C[i] * 100) if i >= k24 else np.nan,
                  (t // 3600) % 24, ((t // 86400) + 3) % 7]
    return sym, out


if __name__ == "__main__":
    z = dict(np.load(f"{ST}/wf/rbs_{TFH}.npz"))   # once: NpzFile decompresses on every access
    by = {}
    for k, sy in enumerate(z["sym"]):
        by.setdefault(sy, []).append(k)
    jobs = [(sy, [(float(z["t"][k]), int(z["side"][k]), int(z["N"][k]), float(z["rg"][k]), float(z["brk"][k])) for k in ks]) for sy, ks in by.items()]
    X = np.full((len(z["t"]), len(NAMES)), np.nan, np.float32)
    with Pool(4) as P:
        for sy, out in P.imap_unordered(run, jobs):
            X[by[sy]] = out
            print(sy, len(out), flush=True)
    np.savez_compressed(f"{ST}/wf/rbs_{TFH}_X.npz", X=X, names=np.array(NAMES))
    print(f"feat {TFH}h done: {np.isfinite(X).all(1).mean():.3f} complete rows", flush=True)
