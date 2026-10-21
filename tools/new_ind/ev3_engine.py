"""New indicator hunt, family 3: classic indicators the project never tried, on 4h and 1d bars (UTC-aligned, built
from 1h; only complete bars). The event is seen at the bar's close, entry at the next hour's open by market:
  st_flip   Supertrend(10, 3) flips -> follow          psar_flip  Parabolic SAR (0.02/0.2) flips -> follow
  ichi      close crosses out of the Ichimoku cloud with Tenkan on the same side -> follow
  macd_x    MACD(12,26,9) crosses its signal below zero -> long, above zero -> short
  rsi_div   price lower low / RSI higher low (pivots 5..40 bars apart, RSI < 40) -> long; mirror short
  stoch_x   Stoch %K(14,3) crosses %D below 20 -> long, above 80 -> short
  adx_go    ADX(14) crosses 25 -> the side of the larger DI
  ha_flip   Heikin-Ashi: 3+ red then a green without a lower wick -> long; mirror short
  nr7       an inside NR7 bar, then a close beyond its high / low -> follow
  cci_back  CCI(20) back above -100 after < -200 -> long; mirror short
  bb_back   close back inside the lower Bollinger(20,2) after a close below -> long; mirror short
  kelt_brk  close beyond Keltner (EMA20 +- 2 ATR) for the first time in 20 bars -> follow
fam id = 2 x indicator + (0 for 4h, 1 for 1d). Context features, exits and the file format: ev2_engine."""
import sys, os, time
ARGS = sys.argv[1:]
import numpy as np
from numba import njit
import ev2_engine as E2
from ev2_engine import agg
from common import D

IND = ["st_flip", "psar_flip", "ichi", "macd_x", "rsi_div", "stoch_x", "adx_go", "ha_flip", "nr7", "cci_back", "bb_back", "kelt_brk"]
FAMS = [f"{a}_{tf}" for a in IND for tf in ("4h", "1d")]
FNAMES = E2.FNAMES


def ema_(x, n):
    out = np.empty(len(x)); k = 2 / (n + 1)
    for i in range(len(x)):
        out[i] = x[i] if i == 0 else out[i - 1] + k * (x[i] - out[i - 1])
    return out


def atr_(H, L, C, n=14):
    pc = np.concatenate([[C[0]], C[:-1]])
    tr = np.maximum(H - L, np.maximum(np.abs(H - pc), np.abs(L - pc)))
    out = np.empty(len(C)); a = tr[0]
    for i in range(len(C)):
        a = tr[i] if i == 0 else (a * (n - 1) + tr[i]) / n; out[i] = a
    return out


@njit(cache=True)
def supertrend(H, L, C, atr, m):
    n = len(C); dirn = np.ones(n); up = np.zeros(n); dn = np.zeros(n)
    for i in range(n):
        hl = (H[i] + L[i]) / 2; u = hl - m * atr[i]; d = hl + m * atr[i]
        if i == 0:
            up[i], dn[i] = u, d; continue
        up[i] = max(u, up[i - 1]) if C[i - 1] > up[i - 1] else u
        dn[i] = min(d, dn[i - 1]) if C[i - 1] < dn[i - 1] else d
        if dirn[i - 1] < 0 and C[i] > dn[i - 1]: dirn[i] = 1
        elif dirn[i - 1] > 0 and C[i] < up[i - 1]: dirn[i] = -1
        else: dirn[i] = dirn[i - 1]
    return dirn


@njit(cache=True)
def psar(H, L, af0, afm):
    n = len(H); d = np.ones(n); sar = L[0]; ep = H[0]; af = af0; up = True
    for i in range(1, n):
        sar = sar + af * (ep - sar)
        if up:
            sar = min(sar, L[i - 1], L[i - 2] if i > 1 else L[i - 1])
            if L[i] < sar:
                up = False; sar = ep; ep = L[i]; af = af0
            elif H[i] > ep:
                ep = H[i]; af = min(af + af0, afm)
        else:
            sar = max(sar, H[i - 1], H[i - 2] if i > 1 else H[i - 1])
            if H[i] > sar:
                up = True; sar = ep; ep = H[i]; af = af0
            elif L[i] < ep:
                ep = L[i]; af = min(af + af0, afm)
        d[i] = 1 if up else -1
    return d


def rmax(x, n):
    out = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)): out[i] = x[i - n + 1:i + 1].max()
    return out


def rmin(x, n):
    out = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)): out[i] = x[i - n + 1:i + 1].min()
    return out


def rsi_(C, n=14):
    d = np.diff(C, prepend=C[0]); up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    au = ema_(up, 2 * n - 1); ad = ema_(dn, 2 * n - 1)
    return 100 - 100 / (1 + au / np.maximum(ad, 1e-12))


def pivots_low(L, k=3):
    p = np.zeros(len(L), bool)
    for i in range(k, len(L) - k):
        if L[i] == L[i - k:i + k + 1].min(): p[i] = True
    return p


def tf_events(O, H, L, C):
    """indicator events on one TF: list of (bar index i where it is seen at the close, indicator id, side)"""
    n = len(C); ev = []
    if n < 60: return ev
    atr = atr_(H, L, C)
    def add(mask, k, s):
        for i in np.flatnonzero(np.nan_to_num(mask, nan=0).astype(bool)):
            if i >= 52: ev.append((i, k, s))
    prev = lambda x: np.concatenate([[x[0]], x[:-1]])
    st = supertrend(H, L, C, atr, 3.0); add((st > 0) & (prev(st) < 0), 0, 1); add((st < 0) & (prev(st) > 0), 0, -1)
    ps = psar(H, L, 0.02, 0.2); add((ps > 0) & (prev(ps) < 0), 1, 1); add((ps < 0) & (prev(ps) > 0), 1, -1)
    ten = (rmax(H, 9) + rmin(L, 9)) / 2; kij = (rmax(H, 26) + rmin(L, 26)) / 2
    sa = np.concatenate([np.full(26, np.nan), ((ten + kij) / 2)[:-26]])
    sb = np.concatenate([np.full(26, np.nan), ((rmax(H, 52) + rmin(L, 52)) / 2)[:-26]])
    top, bot = np.fmax(sa, sb), np.fmin(sa, sb)
    add((C > top) & (prev(C) <= prev(top)) & (ten > kij), 2, 1); add((C < bot) & (prev(C) >= prev(bot)) & (ten < kij), 2, -1)
    macd = ema_(C, 12) - ema_(C, 26); sig = ema_(macd, 9)
    add((macd > sig) & (prev(macd) <= prev(sig)) & (macd < 0), 3, 1); add((macd < sig) & (prev(macd) >= prev(sig)) & (macd > 0), 3, -1)
    r = rsi_(C)
    pl, ph = pivots_low(L), pivots_low(-H)
    for piv, lo_arr, s in ((pl, L, 1), (ph, -H, -1)):
        idx = np.flatnonzero(piv)
        for a, b in zip(idx[:-1], idx[1:]):
            if 5 <= b - a <= 40 and lo_arr[b] < lo_arr[a] and (s * (r[b] - r[a]) > 0) and ((r[b] < 40) if s > 0 else (r[b] > 60)):
                i = b + 3   # the pivot is confirmed 3 bars later
                if i < n and i >= 52: ev.append((i, 4, s))
    hh, ll = rmax(H, 14), rmin(L, 14)
    k_ = np.convolve(100 * (C - ll) / np.where(hh > ll, hh - ll, np.nan), np.ones(3) / 3, mode="full")[:n]
    d_ = np.convolve(np.nan_to_num(k_), np.ones(3) / 3, mode="full")[:n]
    add((k_ > d_) & (prev(k_) <= prev(d_)) & (k_ < 20), 5, 1); add((k_ < d_) & (prev(k_) >= prev(d_)) & (k_ > 80), 5, -1)
    upm = np.maximum(H - prev(H), 0); dnm = np.maximum(prev(L) - L, 0)
    pdm = np.where(upm > dnm, upm, 0); mdm = np.where(dnm > upm, dnm, 0)
    pdi = 100 * ema_(pdm, 27) / np.maximum(atr, 1e-12); mdi = 100 * ema_(mdm, 27) / np.maximum(atr, 1e-12)
    dx = 100 * np.abs(pdi - mdi) / np.maximum(pdi + mdi, 1e-12); adx = ema_(dx, 27)
    cr = (adx > 25) & (prev(adx) <= 25); add(cr & (pdi > mdi), 6, 1); add(cr & (mdi > pdi), 6, -1)
    hc = (O + H + L + C) / 4; ho = np.empty(n); ho[0] = (O[0] + C[0]) / 2
    for i in range(1, n): ho[i] = (ho[i - 1] + hc[i - 1]) / 2
    g = hc > ho
    red3 = np.concatenate([[False] * 3, (~g[:-3]) & (~g[1:-2]) & (~g[2:-1])])
    add(g & red3 & (np.minimum(ho, hc) <= L + 1e-12), 7, 1)
    grn3 = np.concatenate([[False] * 3, g[:-3] & g[1:-2] & g[2:-1]])
    add((~g) & grn3 & (np.maximum(ho, hc) >= H - 1e-12), 7, -1)
    rng = H - L
    nr7 = np.concatenate([[False] * 7, [rng[i] <= rng[i - 6:i + 1].min() for i in range(7, n)]]) & (H <= prev(H)) & (L >= prev(L))
    pn = prev(nr7.astype(float)) > 0
    add(pn & (C > prev(H)), 8, 1); add(pn & (C < prev(L)), 8, -1)
    tp = (H + L + C) / 3; ma = np.convolve(tp, np.ones(20) / 20, mode="full")[:n]
    md = np.array([np.abs(tp[max(0, i - 19):i + 1] - ma[i]).mean() for i in range(n)])
    cci = (tp - ma) / np.maximum(0.015 * md, 1e-12)
    was_lo = np.array([cci[max(0, i - 10):i].min() < -200 if i > 0 else False for i in range(n)])
    was_hi = np.array([cci[max(0, i - 10):i].max() > 200 if i > 0 else False for i in range(n)])
    add((cci > -100) & (prev(cci) <= -100) & was_lo, 9, 1); add((cci < 100) & (prev(cci) >= 100) & was_hi, 9, -1)
    sm = np.convolve(C, np.ones(20) / 20, mode="full")[:n]
    sd = np.array([C[max(0, i - 19):i + 1].std() for i in range(n)])
    lb, ub = sm - 2 * sd, sm + 2 * sd
    add((C > lb) & (prev(C) < prev(lb)), 10, 1); add((C < ub) & (prev(C) > prev(ub)), 10, -1)
    e20 = ema_(C, 20); ku, kl = e20 + 2 * atr, e20 - 2 * atr
    above = C > ku; below = C < kl
    first_up = np.array([above[i] and not above[max(0, i - 20):i].any() for i in range(n)])
    first_dn = np.array([below[i] and not below[max(0, i - 20):i].any() for i in range(n)])
    add(first_up, 11, 1); add(first_dn, 11, -1)
    return ev


def ev3_events(c):
    T, O, H, L, C, n = c["T"], c["O"], c["H"], c["L"], c["C"], c["n"]
    out = []
    for tfi, sec in ((0, 4 * 3600), (1, 86400)):
        pid = T // sec
        g = agg(pid, O, H, L, C)
        st, en = g[5], g[6]
        full = (en - st) == sec // 3600
        evs = tf_events(g[1], g[2], g[3], g[4])
        for i, k, s in evs:
            if not full[i]: continue
            j = en[i] - 1
            if j + 1 < n: out.append((int(j), 2 * k + tfi, s))
    return out


E2.EVENTS[0] = ev3_events
E2.OUT[0] = f"{D}/ev3"

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
