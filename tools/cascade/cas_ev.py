"""EMA cascade (EMA 5/10/14/20/28 on 1h): every close that crosses the WHOLE cascade (all five EMAs) — down (a short) or
up (a long) — with its context and outcomes. Context: the 48-bar range in ATR (the pump), how many of the last 48 bars
had the ribbon ordered the other way (the prior trend), bars since the opposite whole-cascade cross (a break-and-reject),
the excursion past the cascade before the cross, BTC's 24h move. Outcomes: entry at the next bar's open, stops
1 / 1.5 / 2 ATR and the 24-bar swing extreme, takes 1 / 2 / 3R, the cascade exit (a close back past the far EMA), 24 / 48 h."""
import os, sys, numpy as np, multiprocessing as mp
ARGS = sys.argv[1:]
from numba import njit
from common import load, D
NS = (5, 10, 14, 20, 28)
STOPS = (1.0, 1.5, 2.0, -1.0)            # -1 = the 24-bar swing extreme (+0.2 ATR)
EXITS = ("t1", "t2", "t3", "cas")
HOLDS = (24, 48)
def ema(x, n):
    a = 2 / (n + 1); out = np.empty_like(x); e = x[0]
    for i in range(len(x)): e = x[i] if i == 0 else e + a * (x[i] - e); out[i] = e
    return out
@njit(cache=True)
def label(O, H, L, C, TOP, BOT, i, s, a, stop_k, ex, hold):
    n = len(C); e = O[i + 1]
    if stop_k > 0: stop = e - s * stop_k * a
    else:
        lo = L[i]; hi = H[i]
        for k in range(max(0, i - 23), i + 1):
            if L[k] < lo: lo = L[k]
            if H[k] > hi: hi = H[k]
        stop = (lo - 0.2 * a) if s > 0 else (hi + 0.2 * a)
    risk = s * (e - stop)
    if risk <= e * 0.002: return np.nan, 0
    W = min(hold, n - i - 2)
    if W < hold: return np.nan, 0
    k = W - 1; px = C[i + 1 + k]
    for q in range(W):
        b = i + 1 + q
        if (s > 0 and L[b] <= stop) or (s < 0 and H[b] >= stop):
            px = O[b] if (q > 0 and ((s > 0 and O[b] <= stop) or (s < 0 and O[b] >= stop))) else stop; k = q; break
        if ex > 0:
            tp = e + s * ex * risk
            if (s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp): px = tp; k = q; break
        elif (s > 0 and C[b] < BOT[b]) or (s < 0 and C[b] > TOP[b]):
            px = C[b]; k = q; break
    return (s * (px - e) - (0.001 + 0.0003 * (k + 1) / 24) * e) / risk, k + 1
def run(sym):
    fn = f"{D}/cas/{sym}.npz"
    if os.path.exists(fn): return sym, -1
    cs = load(sym)
    if not cs or len(cs) < 24 * 100: return sym, 0
    O = np.array([c["open"] for c in cs]); H = np.array([c["high"] for c in cs]); L = np.array([c["low"] for c in cs]); C = np.array([c["close"] for c in cs])
    T = np.array([c["time"] + 3600 for c in cs])
    E = np.stack([ema(C, n) for n in NS]); TOP, BOT = E.max(0), E.min(0)
    tr = np.maximum(H[1:] - L[1:], np.maximum(abs(H[1:] - C[:-1]), abs(L[1:] - C[:-1]))); tr = np.r_[H[0] - L[0], tr]
    atr = np.full(len(C), np.nan); a = tr[:14].mean()
    for i in range(14, len(C)): a = (a * 13 + tr[i]) / 14; atr[i] = a
    bull = np.all(np.diff(E[::-1], axis=0) > 0, axis=0)   # EMA28 < EMA20 < 14 < 10 < 5: the ribbon ordered up
    bear = np.all(np.diff(E[::-1], axis=0) < 0, axis=0)
    up = (C > TOP) & (np.r_[False, C[:-1] <= TOP[:-1]])
    dn = (C < BOT) & (np.r_[False, C[:-1] >= BOT[:-1]])
    btc = load("BTCUSDT"); bt = np.array([c["time"] + 3600 for c in btc]); bc = np.array([c["close"] for c in btc])
    rows, Y = [], []
    last_up, last_dn = -10 ** 6, -10 ** 6
    for i in range(300, len(C) - 50):
        if up[i - 1]: last_up = i - 1
        if dn[i - 1]: last_dn = i - 1
        if not (up[i] or dn[i]) or atr[i] != atr[i]: continue
        s = 1 if up[i] else -1
        w = slice(i - 48, i)
        rng = (H[w].max() - L[w].min()) / atr[i]
        prior = (bear[w].sum() if s > 0 else bull[w].sum())          # the opposite trend before the cross
        since_opp = i - (last_dn if s > 0 else last_up)               # bars since the opposite whole-cascade cross
        exc = ((TOP[w] - L[w]).max() if s > 0 else (H[w] - BOT[w]).max()) / atr[i]   # the excursion past the cascade before (the pump/dump)
        move24 = s * (C[i] - C[i - 24]) / atr[i]
        width = (TOP[i] - BOT[i]) / atr[i]
        j = np.searchsorted(bt, T[i]) - 1
        b24 = s * (bc[j] / bc[j - 24] - 1) * 100 if j >= 24 else 0.0
        y = np.full((len(STOPS), len(EXITS), len(HOLDS)), np.nan, np.float32)
        for si, sk in enumerate(STOPS):
            for xi, xn in enumerate(EXITS):
                for hi_, h in enumerate(HOLDS):
                    y[si, xi, hi_] = label(O, H, L, C, TOP, BOT, i, s, atr[i], sk, float(xn[1:]) if xn[0] == "t" else 0.0, h)[0]
        rows.append([T[i], s, rng, prior, min(since_opp, 999), exc, move24, width, b24, atr[i] / C[i] * 100]); Y.append(y)
    np.savez_compressed(fn, F=np.array(rows, dtype=np.float64), Y=np.array(Y, dtype=np.float32))
    return sym, len(rows)
if __name__ == "__main__":
    os.makedirs(f"{D}/cas", exist_ok=True)
    syms = ARGS or sorted(f[:-4] for f in os.listdir(f"{D}/data/1h"))
    with mp.Pool(4) as p:
        for r in p.imap_unordered(run, syms): print(*r, flush=True)
