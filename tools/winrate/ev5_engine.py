"""New indicator hunt, family 5: Lorentzian Classification (jdehorty, TradingView / GitHub, the most-liked ML script) on
1h, 4h and 1d bars (UTC-aligned, built from 1h; only complete bars). Seen at the bar's close, entry at the next hour's
open by market. Per bar the 5 default features (RSI 14, WaveTrend 10/11, CCI 20, ADX 20, RSI 9; each scaled with its
own history only), the 8 nearest past bars by the Lorentzian distance sum(log(1 + |a - b|)) among the last 2000 bars
(every 4th, as the script), each labelled by the sign of its NEXT 4 bars -- only bars whose 4 bars have already closed
(the honest form of the script's label); prediction = the labels' sum (-8..8). The signal: long when the prediction > 0
and the Nadaraya-Watson rational-quadratic kernel (h 8, r 8, the script's defaults) rises, short when < 0 and it falls,
else unchanged; the event = the signal changes. Simplified: no ANN quirks, no volatility / regime / ADX filters (all
the script's options), the kernel always on.
fam = 2 x tf (0 1h, 1 4h, 2 1d) + (|prediction| == 8). Context features, exits, file format: ev2_engine."""
import sys, os, time
ARGS = sys.argv[1:]
import numpy as np
from numba import njit
import ev3_engine as E3
import ev2_engine as E2
from ev2_engine import agg
from ev3_engine import ema_, rsi_
from common import D

TFS = (("1h", 3600), ("4h", 4 * 3600), ("1d", 86400))
FAMS = [f"lc_{tf}{'_8' if s else ''}" for tf, _ in TFS for s in (0, 1)]


def sma_(x, n):
    c = np.cumsum(np.insert(np.nan_to_num(x), 0, 0.0)); out = np.full(len(x), np.nan)
    if len(x) >= n: out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def rma_(x, n):
    out = np.full(len(x), np.nan); s = np.nan
    for i in range(len(x)):
        v = x[i]
        if not np.isfinite(v): continue
        s = v if not np.isfinite(s) else (s * (n - 1) + v) / n
        out[i] = s
    return out


def run_minmax(x):
    """the script's normalize(): (x - min so far) / (max so far - min so far) -- the history up to the bar only"""
    lo = np.fmin.accumulate(np.where(np.isfinite(x), x, np.inf))
    hi = np.fmax.accumulate(np.where(np.isfinite(x), x, -np.inf))
    return np.where(hi > lo, (x - lo) / np.where(hi > lo, hi - lo, 1), 0.5)


def feats(H, L, C):
    f1 = ema_(rsi_(C, 14), 1) / 100; f5 = ema_(rsi_(C, 9), 1) / 100
    hlc = (H + L + C) / 3; esa = ema_(hlc, 10); d = ema_(np.abs(hlc - esa), 10)
    ci = (hlc - esa) / np.maximum(0.015 * d, 1e-12); wt1 = ema_(ci, 11); wt2 = sma_(wt1, 4)
    f2 = run_minmax(wt1 - wt2)
    tp = hlc; m20 = sma_(tp, 20)
    md = np.full(len(C), np.nan)
    for i in range(19, len(C)): md[i] = np.abs(tp[i - 19:i + 1] - m20[i]).mean()
    cci = (tp - m20) / np.maximum(0.015 * md, 1e-12)
    f3 = run_minmax(ema_(np.nan_to_num(cci), 1))
    pc = np.concatenate([[C[0]], C[:-1]]); ph = np.concatenate([[H[0]], H[:-1]]); pl = np.concatenate([[L[0]], L[:-1]])
    tr = np.maximum(H - L, np.maximum(np.abs(H - pc), np.abs(L - pc)))
    up, dn = H - ph, pl - L
    dmp = np.where((up > dn) & (up > 0), up, 0.0); dmm = np.where((dn > up) & (dn > 0), dn, 0.0)
    atr = rma_(tr, 20); dip = 100 * rma_(dmp, 20) / atr; dim = 100 * rma_(dmm, 20) / atr
    dx = 100 * np.abs(dip - dim) / np.maximum(dip + dim, 1e-12)
    f4 = rma_(dx, 20) / 100
    return np.nan_to_num(np.vstack([f1, f2, f3, f4, f5]).T, nan=0.5)


@njit(cache=True)
def knn_pred(Fx, C, look, k, step, fwd):
    n = len(C); pred = np.zeros(n)
    dist = np.empty(look // step + 2); lab = np.empty(look // step + 2)
    for t in range(n):
        m = 0
        lo = max(0, t - look)
        for i in range(lo, t - fwd + 1):   # label known: bar i + fwd has closed by bar t
            if i % step != 0: continue
            d = 0.0
            for q in range(Fx.shape[1]):
                d += np.log(1.0 + abs(Fx[t, q] - Fx[i, q]))
            dist[m] = d
            lab[m] = 1.0 if C[i + fwd] > C[i] else (-1.0 if C[i + fwd] < C[i] else 0.0)
            m += 1
        if m < k: continue
        o = np.argsort(dist[:m])[:k]
        s = 0.0
        for q in range(k): s += lab[o[q]]
        pred[t] = s
    return pred


@njit(cache=True)
def kernel_rq(C, h, r, start):
    n = len(C); y = np.full(n, np.nan)
    w = np.empty(start + 1)
    for i in range(start + 1): w[i] = (1 + i * i / (h * h * 2 * r)) ** (-r)
    for t in range(start, n):
        a = 0.0; b = 0.0
        for i in range(start + 1):
            a += C[t - i] * w[i]; b += w[i]
        y[t] = a / b
    return y


def tf_events(O, H, L, C, V):
    n = len(C); ev = []
    if n < 300: return ev
    Fx = feats(H, L, C)
    pred = knn_pred(Fx, C, 2000, 8, 4, 4)
    yk = kernel_rq(C, 8.0, 8.0, 25)
    rise = np.concatenate([[False], yk[1:] > yk[:-1]]); fall = np.concatenate([[False], yk[1:] < yk[:-1]])
    sig = np.zeros(n)
    for i in range(1, n):
        sig[i] = 1 if (pred[i] > 0 and rise[i]) else (-1 if (pred[i] < 0 and fall[i]) else sig[i - 1])
    for i in range(260, n):
        if sig[i] != 0 and sig[i] != sig[i - 1]:
            ev.append((i, int(abs(pred[i]) >= 8), int(sig[i])))
    return ev


def ev5_events(c):
    T, O, H, L, C, V, n = c["T"], c["O"], c["H"], c["L"], c["C"], c["V"], c["n"]
    out = []
    for tfi, (_, sec) in enumerate(TFS):
        pid = T // sec
        g = agg(pid, O, H, L, C)
        st, en = g[5], g[6]
        full = (en - st) == sec // 3600
        cv = np.cumsum(np.insert(V, 0, 0.0)); gv = cv[en] - cv[st]
        for i, k, s in tf_events(g[1], g[2], g[3], g[4], gv):
            if not full[i]: continue
            j = en[i] - 1
            if j + 1 < n: out.append((int(j), 2 * tfi + k, s))
    return out


E2.EVENTS[0] = ev5_events
E2.OUT[0] = f"{D}/ev5"

if __name__ == "__main__":
    import json, multiprocessing as mp
    os.makedirs(E2.OUT[0], exist_ok=True)
    sp = json.load(open(f"{D}/lv/split.json"))
    syms = ARGS or (sp["bot"] + sp["chk"])
    t0 = time.time()
    if len(syms) == 1:
        print(E2.run(syms[0]), time.time() - t0)
    else:
        with mp.Pool(4) as pool:
            for k, (s, m) in enumerate(pool.imap_unordered(E2.run, syms)):
                if k % 30 == 0: print(k, s, m, round(time.time() - t0), flush=True)
    print("done", round(time.time() - t0))
