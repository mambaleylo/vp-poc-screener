"""New indicator hunt, family 4: popular open-source indicators (GitHub freqtrade strategies, TradingView community
scripts) on 1h, 4h and 1d bars (UTC-aligned, built from 1h; only complete bars). Seen at the bar's close, entry at the
next hour's open by market:
  ut_bot    UT Bot alerts (ATR trailing stop, key 2, ATR 10): close crosses the stop -> follow
  ssl       SSL channel (SMA 10 of highs / lows) flips -> follow
  wt_x      WaveTrend (LazyBear 10/21): wt1 crosses wt2 below -60 -> long, above 60 -> short
  sqz_rel   Squeeze Momentum (LazyBear): BB(20,2) inside KC(20,1.5) for 6+ bars, then out -> the momentum's side
  rng_flt   Range Filter (DonovanWall, 100 / 3): the filter turns -> follow
  chand     Chandelier Exit (everget, 22 / 3) flips -> follow
  wvf       Williams Vix Fix (ChrisMoody): a bottom spike ends (was >= BB top / 85% of the 50-bar high, now under) -> long;
            the inverse (top) -> short
  td9       TD Sequential setup 9 (9 closes < the close 4 bars before) -> long; mirror short
  crsi      Connors RSI (3, 2, 100) < 10 -> long; > 90 -> short
  binhv45   freqtrade BinHV45 (BB 40 lower, bbdelta / closedelta / tail) -> long; mirror short
  cluc      freqtrade ClucMay72018: close < EMA100 and < 0.985 x BB(20,2) lower, volume < 20 x mean -> long; mirror
  ewo_dip   freqtrade SMAOffset / NFI style: close < EMA16 x 0.973, EWO(5,35) > 5.6, RSI < 50 -> long; mirror
  sfp       swing failure: the low takes the 20-bar low and the close is back above it -> long; mirror short
  fisher_x  Ehlers Fisher (9) crosses up from below -2 -> long; down from above 2 -> short
  hma_flip  Hull MA (55) turns -> follow
  qqe       QQE (14, 5, 4.236): the smoothed RSI crosses its trailing line -> follow
fam id = 3 x indicator + (0 1h, 1 4h, 2 1d). Context features, exits and the file format: ev2_engine."""
import sys, os, time
ARGS = sys.argv[1:]
import numpy as np
from numba import njit
import ev3_engine as E3
import ev2_engine as E2
from ev2_engine import agg
from ev3_engine import ema_, atr_, rmax, rmin, rsi_
from common import D

IND = ["ut_bot", "ssl", "wt_x", "sqz_rel", "rng_flt", "chand", "wvf", "td9", "crsi", "binhv45", "cluc", "ewo_dip", "sfp",
       "fisher_x", "hma_flip", "qqe"]
TFS = (("1h", 3600), ("4h", 4 * 3600), ("1d", 86400))
FAMS = [f"{a}_{tf}" for a in IND for tf, _ in TFS]
FNAMES = E2.FNAMES


def sma_(x, n):
    c = np.cumsum(np.insert(np.nan_to_num(x), 0, 0.0)); out = np.full(len(x), np.nan)
    out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def rstd_(x, n):
    m = sma_(x, n); m2 = sma_(x * x, n)
    return np.sqrt(np.maximum(m2 - m * m, 0))


def wma_(x, n):
    w = np.arange(1, n + 1, dtype=float); out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1:] = np.convolve(x, w[::-1], mode="valid") / w.sum()
    return out


@njit(cache=True)
def ut_trail(C, atr, key):
    n = len(C); st = np.empty(n); st[0] = C[0]
    for i in range(1, n):
        nl = key * atr[i]
        if C[i] > st[i - 1] and C[i - 1] > st[i - 1]: st[i] = max(st[i - 1], C[i] - nl)
        elif C[i] < st[i - 1] and C[i - 1] < st[i - 1]: st[i] = min(st[i - 1], C[i] + nl)
        elif C[i] > st[i - 1]: st[i] = C[i] - nl
        else: st[i] = C[i] + nl
    return st


@njit(cache=True)
def rng_filter(C, rng):
    n = len(C); f = np.empty(n); f[0] = C[0]
    for i in range(1, n):
        r = rng[i] if rng[i] == rng[i] else 0.0
        if C[i] > f[i - 1]: f[i] = f[i - 1] if C[i] - r < f[i - 1] else C[i] - r
        else: f[i] = f[i - 1] if C[i] + r > f[i - 1] else C[i] + r
    return f


@njit(cache=True)
def chandelier(H, L, C, atr, n_, m):
    n = len(C); d = np.zeros(n); ls = np.zeros(n); ss = np.zeros(n)
    for i in range(n):
        a = max(0, i - n_ + 1); hh = H[a:i + 1].max(); ll = L[a:i + 1].min()
        l_ = hh - m * atr[i]; s_ = ll + m * atr[i]
        if i == 0:
            ls[i] = l_; ss[i] = s_; d[i] = 1; continue
        ls[i] = max(l_, ls[i - 1]) if C[i - 1] > ls[i - 1] else l_
        ss[i] = min(s_, ss[i - 1]) if C[i - 1] < ss[i - 1] else s_
        d[i] = 1 if C[i] > ss[i - 1] else (-1 if C[i] < ls[i - 1] else d[i - 1])
    return d


@njit(cache=True)
def fisher(H, L, n_):
    n = len(H); v = np.zeros(n); f = np.zeros(n)
    hl = (H + L) / 2
    for i in range(n):
        a = max(0, i - n_ + 1); hh = hl[a:i + 1].max(); ll = hl[a:i + 1].min()
        x = 0.66 * ((hl[i] - ll) / max(hh - ll, 1e-12) - 0.5) + 0.67 * (v[i - 1] if i > 0 else 0.0)
        x = min(max(x, -0.999), 0.999); v[i] = x
        f[i] = 0.5 * np.log((1 + x) / (1 - x)) + 0.5 * (f[i - 1] if i > 0 else 0.0)
    return f


@njit(cache=True)
def qqe_line(rs, dar):
    n = len(rs); tl = np.zeros(n)
    for i in range(1, n):
        nl = rs[i] - dar[i]; ns = rs[i] + dar[i]
        if rs[i - 1] > tl[i - 1] and rs[i] > tl[i - 1]: tl[i] = max(tl[i - 1], nl)
        elif rs[i - 1] < tl[i - 1] and rs[i] < tl[i - 1]: tl[i] = min(tl[i - 1], ns)
        elif rs[i] > tl[i - 1]: tl[i] = nl
        else: tl[i] = ns
    return tl


def tf_events(O, H, L, C, V):
    n = len(C); ev = []
    if n < 260: return ev
    atr = atr_(H, L, C)
    def add(mask, k, s):
        for i in np.flatnonzero(np.nan_to_num(mask, nan=0).astype(bool)):
            if i >= 210: ev.append((i, k, s))
    prev = lambda x: np.concatenate([[x[0]], x[:-1]])
    # 0 UT Bot
    st = ut_trail(C, atr_(H, L, C, 10), 2.0)
    add((C > st) & (prev(C) <= prev(st)), 0, 1); add((C < st) & (prev(C) >= prev(st)), 0, -1)
    # 1 SSL
    sh, sl = sma_(H, 10), sma_(L, 10); hlv = np.zeros(n)
    for i in range(1, n): hlv[i] = 1 if C[i] > sh[i] else (-1 if C[i] < sl[i] else hlv[i - 1])
    add((hlv > 0) & (prev(hlv) < 0), 1, 1); add((hlv < 0) & (prev(hlv) > 0), 1, -1)
    # 2 WaveTrend
    ap = (H + L + C) / 3; esa = ema_(ap, 10); d = ema_(np.abs(ap - esa), 10)
    ci = (ap - esa) / np.maximum(0.015 * d, 1e-12); wt1 = ema_(ci, 21); wt2 = sma_(wt1, 4)
    add((wt1 > wt2) & (prev(wt1) <= prev(wt2)) & (wt1 < -60), 2, 1); add((wt1 < wt2) & (prev(wt1) >= prev(wt2)) & (wt1 > 60), 2, -1)
    # 3 Squeeze release
    bm = sma_(C, 20); bs = rstd_(C, 20); tr_ = atr_(H, L, C, 20)
    sqz = ((bm + 2 * bs) < (bm + 1.5 * tr_)) & ((bm - 2 * bs) > (bm - 1.5 * tr_))
    run_ = np.zeros(n, int)
    for i in range(1, n): run_[i] = run_[i - 1] + 1 if sqz[i] else 0
    rel = (~sqz) & (prev(run_) >= 6)
    mid = ((rmax(H, 20) + rmin(L, 20)) / 2 + bm) / 2; dev = C - mid
    mom = np.full(n, np.nan); xs = np.arange(20) - 9.5
    for i in range(19, n):
        y = dev[i - 19:i + 1]
        if np.all(np.isfinite(y)): mom[i] = (xs * (y - y.mean())).sum() / (xs * xs).sum() * 9.5 + y.mean()
    add(rel & (mom > 0), 3, 1); add(rel & (mom < 0), 3, -1)
    # 4 Range Filter
    ac = np.abs(C - prev(C)); rng = ema_(ema_(ac, 100), 199) * 3.0
    f = rng_filter(C, rng); fd = np.sign(f - prev(f)); upw = np.zeros(n)
    for i in range(1, n): upw[i] = fd[i] if fd[i] != 0 else upw[i - 1]
    add((upw > 0) & (prev(upw) < 0) & (C > f), 4, 1); add((upw < 0) & (prev(upw) > 0) & (C < f), 4, -1)
    # 5 Chandelier
    cd = chandelier(H, L, C, atr_(H, L, C, 22), 22, 3.0)
    add((cd > 0) & (prev(cd) < 0), 5, 1); add((cd < 0) & (prev(cd) > 0), 5, -1)
    # 6 Williams Vix Fix (bottom) / inverse (top)
    hc = rmax(C, 22); wvf = (hc - L) / hc * 100
    wu = sma_(wvf, 20) + 2 * rstd_(wvf, 20); ext = (wvf >= wu) | (wvf >= 0.85 * rmax(wvf, 50))
    add((prev(ext.astype(float)) > 0) & ~ext, 6, 1)
    lc = rmin(C, 22); iwv = (H - lc) / lc * 100
    iu = sma_(iwv, 20) + 2 * rstd_(iwv, 20); iext = (iwv >= iu) | (iwv >= 0.85 * rmax(iwv, 50))
    add((prev(iext.astype(float)) > 0) & ~iext, 6, -1)
    # 7 TD setup 9
    c4 = np.concatenate([np.full(4, np.nan), C[:-4]]); bu = np.zeros(n, int); se = np.zeros(n, int)
    for i in range(4, n):
        bu[i] = bu[i - 1] + 1 if C[i] < c4[i] else 0; se[i] = se[i - 1] + 1 if C[i] > c4[i] else 0
    add(bu == 9, 7, 1); add(se == 9, 7, -1)
    # 8 Connors RSI
    r3 = rsi_(C, 3); stk = np.zeros(n)
    for i in range(1, n):
        stk[i] = (stk[i - 1] + 1 if stk[i - 1] > 0 else 1) if C[i] > C[i - 1] else ((stk[i - 1] - 1 if stk[i - 1] < 0 else -1) if C[i] < C[i - 1] else 0)
    rs2 = rsi_(stk + 100.0, 2)
    roc = C / prev(C) - 1; pr = np.full(n, 50.0)
    for i in range(100, n): pr[i] = (roc[i - 100:i] < roc[i]).mean() * 100
    crsi = (r3 + rs2 + pr) / 3
    add((crsi < 10) & (prev(crsi) >= 10), 8, 1); add((crsi > 90) & (prev(crsi) <= 90), 8, -1)
    # 9 BinHV45 (mirror for shorts)
    m40 = sma_(C, 40); s40 = rstd_(C, 40); lo40, up40 = m40 - 2 * s40, m40 + 2 * s40
    bbd = m40 - lo40; cdl = np.abs(C - prev(C))
    add((bbd > C * 0.008) & (cdl > C * 0.0175) & (np.abs(C - L) < bbd * 0.25) & (C < prev(lo40)) & (C <= prev(C)), 9, 1)
    add((bbd > C * 0.008) & (cdl > C * 0.0175) & (np.abs(H - C) < bbd * 0.25) & (C > prev(up40)) & (C >= prev(C)), 9, -1)
    # 10 ClucMay72018
    e100 = ema_(C, 100); lo20, up20 = bm - 2 * bs, bm + 2 * bs
    vm = prev(sma_(V, 30))
    add((C < e100) & (C < 0.985 * lo20) & (V < vm * 20), 10, 1); add((C > e100) & (C > 1.015 * up20) & (V < vm * 20), 10, -1)
    # 11 EWO dip
    ewo = (ema_(C, 5) - ema_(C, 35)) / C * 100; e16 = ema_(C, 16); r14 = rsi_(C, 14)
    dip = (C < e16 * 0.973) & (ewo > 5.6) & (r14 < 50); pump = (C > e16 * 1.027) & (ewo < -5.6) & (r14 > 50)
    add(dip & ~(prev(dip.astype(float)) > 0), 11, 1); add(pump & ~(prev(pump.astype(float)) > 0), 11, -1)
    # 12 swing failure
    pl = prev(rmin(L, 20)); ph = prev(rmax(H, 20))
    add((L < pl) & (C > pl) & (C > O), 12, 1); add((H > ph) & (C < ph) & (C < O), 12, -1)
    # 13 Fisher
    fi = fisher(H, L, 9); fs = prev(fi)
    add((fi > fs) & (prev(fi) <= prev(fs)) & (fs < -2), 13, 1); add((fi < fs) & (prev(fi) >= prev(fs)) & (fs > 2), 13, -1)
    # 14 Hull MA
    hm = wma_(2 * wma_(C, 27) - wma_(C, 55), 7); sl_ = np.sign(hm - prev(hm))
    add((sl_ > 0) & (prev(sl_) < 0), 14, 1); add((sl_ < 0) & (prev(sl_) > 0), 14, -1)
    # 15 QQE
    rs = ema_(rsi_(C, 14), 5); ar = np.abs(rs - prev(rs)); dar = ema_(ema_(ar, 27), 27) * 4.236
    tl = qqe_line(rs, dar)
    add((rs > tl) & (prev(rs) <= prev(tl)), 15, 1); add((rs < tl) & (prev(rs) >= prev(tl)), 15, -1)
    return ev


def ev4_events(c):
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
            if j + 1 < n: out.append((int(j), 3 * k + tfi, s))
    return out


E2.EVENTS[0] = ev4_events
E2.OUT[0] = f"{D}/ev4"

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
