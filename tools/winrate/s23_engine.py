"""Win-rate hunt (the user: "главная цель только винрейт и количество сделок… хоть минутный тайм фрейм… rr не важен, главное
положительный"): short-term mean-reversion / pullback entries on 15m bars of the 127 coins, each with small takes and wide
stops. The event is seen at the close of bar i; a limit order lives for the next W bars (filled = the bar's low / high
reached it; a bar that opens beyond it fills at its open); only filled orders are kept.
  deep2 / deep3   a limit 2 / 3 x ATR(15m) from the close (catching a wick), W = 4 bars
  bb              a limit at the Bollinger(20, 2.5) band of bar i, W = 1
  ema_pb          trend (EMA50 above EMA200, the close above EMA20): a limit at EMA20, W = 2 (mirror short)
  vwap2           a limit at the day's VWAP -/+ 2 sigma (of close - VWAP over 96 bars), W = 1
  sweep           bar i swept the 24 h low / high and closed back inside: market at the next open
Exits from the fill (ATR of bar i): E0 take 0.5 / stop 2.0 ATR / 16 bars, E1 1.0 / 2.0 / 32, E2 0.3 / 1.5 / 8,
E3 0.5 / 1.0 / 16, E4 0.2 / 2.0 / 8. In the fill bar only the stop counts. R per the stop distance, fees: a limit entry
0.02% (market 0.05%), the take 0.02% (a limit), a stop / time exit 0.05%, funding 0.03%/day.
Saved per coin to s15/<SYM>.npz: t, side, fam, R[exits], K[exits] (hours, for the busy / bootstrap logic), W[exits]
(1 = take), F (features)."""
import sys, os, time
ARGS = sys.argv[1:]
import numpy as np
from numba import njit
from common import D
TFH = int(os.environ.get("TFH", "4"))

FAMS = ["w05", "w075", "w1", "w125", "w15"]
DEP = [0.5, 0.75, 1.0, 1.25, 1.5]
EXITS = ((1.0, 2.0, 32), (1.25, 2.0, 48))
FNAMES = ["fam", "side", "atrp", "datr", "depth", "hour", "dow", "r1h", "r4h", "r24h", "e20", "e50", "e200", "sl50", "rsi", "rsi4",
          "bbz", "vwz", "pos96", "volr", "b4h", "b24h", "batr", "wick", "rng", "since", "r7d", "dpos30"]
OUT = f"{D}/s23_{TFH}h" + os.environ.get("SUF", "")


def load15(sym):
    """4h bars from the 1h file (UTC 4h blocks, complete ones only)"""
    a = np.loadtxt(f"{D}/data/1h/{sym}.csv", delimiter=",", ndmin=2)
    t = a[:, 0].astype(np.int64)
    k = np.concatenate([[True], np.diff(t) > 0])
    a = a[k]; t = a[:, 0].astype(np.int64)
    blk = t // (TFH * 3600)
    st = np.concatenate([[0], np.flatnonzero(blk[1:] != blk[:-1]) + 1]); en = np.concatenate([st[1:], [len(t)]])
    full = (en - st) == TFH
    st, en = st[full], en[full]
    T4 = blk[st] * (TFH * 3600)
    O4 = a[st, 1]; H4 = np.maximum.reduceat(a[:, 2], st)[: len(st)] if False else np.array([a[s:e, 2].max() for s, e in zip(st, en)])
    L4 = np.array([a[s:e, 3].min() for s, e in zip(st, en)]); C4 = a[en - 1, 4]; V4 = np.array([a[s:e, 5].sum() for s, e in zip(st, en)])
    return T4, O4, H4, L4, C4, V4


@njit
def wilder(H, L, C, n):
    out = np.full(len(C), np.nan)
    if len(C) <= n:
        return out
    s = 0.0
    for i in range(n):
        s += (H[i] - L[i]) if i == 0 else max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1]))
    a = s / n; out[n - 1] = a
    for i in range(n, len(C)):
        tr = max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1]))
        a = (a * (n - 1) + tr) / n; out[i] = a
    return out


@njit
def ema(x, n):
    out = np.empty(len(x)); k = 2.0 / (n + 1); e = x[0]
    for i in range(len(x)):
        e = x[i] if i == 0 else e + k * (x[i] - e); out[i] = e
    return out


@njit
def rsi(C, n):
    out = np.full(len(C), 50.0)
    au = 0.0; ad = 0.0
    for i in range(1, len(C)):
        d = C[i] - C[i - 1]; u = d if d > 0 else 0.0; dn = -d if d < 0 else 0.0
        if i <= n:
            au += u / n; ad += dn / n
        else:
            au = (au * (n - 1) + u) / n; ad = (ad * (n - 1) + dn) / n
        if i >= n:
            out[i] = 100 - 100 / (1 + au / ad) if ad > 0 else 100.0
    return out


@njit
def roll_std(x, n):
    out = np.full(len(x), np.nan); s = 0.0; s2 = 0.0
    for i in range(len(x)):
        s += x[i]; s2 += x[i] * x[i]
        if i >= n:
            s -= x[i - n]; s2 -= x[i - n] * x[i - n]
        if i >= n - 1:
            m = s / n; v = s2 / n - m * m
            out[i] = np.sqrt(v) if v > 0 else 0.0
    return out


@njit
def roll_minmax(H, L, n):
    """max high / min low of the n bars BEFORE i"""
    hi = np.full(len(H), np.nan); lo = np.full(len(H), np.nan)
    for i in range(n, len(H)):
        hi[i] = H[i - n:i].max(); lo[i] = L[i - n:i].min()
    return hi, lo


@njit
def simulate(O, H, L, C, f, side, fill, atr, take, stop, hold, fee_in, bpd):
    """from the fill bar f: (R, bars held, took)"""
    n = len(C); risk = stop * atr
    sl = fill - side * risk; tp = fill + side * take * atr
    e = min(n, f + hold); k = e - 1 - f; ex = C[e - 1]; win = 0; fee_out = 0.0005
    for q in range(e - f):
        b = f + q
        if (side > 0 and L[b] <= sl) or (side < 0 and H[b] >= sl):
            gap = (side > 0 and O[b] <= sl) or (side < 0 and O[b] >= sl)
            ex = O[b] if (gap and q > 0) else sl; k = q; break
        if q > 0 and ((side > 0 and H[b] >= tp) or (side < 0 and L[b] <= tp)):
            ex = tp; k = q; win = 1; fee_out = 0.0002; break
    fees = (fee_in + fee_out + 0.0003 * (k + 1) / bpd) * fill
    return (side * (ex - fill) - fees) / risk, k + 1, win


@njit
def fills(L, H, lv, side, W):
    n = len(lv); fb = np.full(n, -1, np.int64)
    for j in range(300, n - 1):
        x = lv[j]
        if not (x == x): continue
        for b in range(j + 1, min(j + W, n - 1) + 1):
            if (side > 0 and L[b] <= x) or (side < 0 and H[b] >= x):
                fb[j] = b; break
    return fb


@njit
def bot_since(fb, W):
    n = len(fb); out = np.full(n, 999.0); s_last = -1; s_busy = -1
    for i0 in range(300, n):
        j = i0 - W - 1
        if j >= 300 and s_busy <= j and fb[j] != -1:
            s_last = j; s_busy = fb[j] + 1
        last = s_last; busy = s_busy
        for jj in range(max(300, i0 - W), i0):
            if busy <= jj and fb[jj] != -1 and fb[jj] <= i0:
                last = jj; busy = fb[jj] + 1
        if busy > i0:
            out[i0] = -1.0
        elif last >= 0:
            out[i0] = min(999.0, float(i0 - last))
    return out


_B = {}
def btc():
    if not _B:
        T, O, H, L, C, V = load15("BTCUSDT")
        _B.update(T=T, C=C, atr=wilder(H, L, C, 14))
    return _B


def run(sym):
    fn = f"{OUT}/{sym}.npz"
    if os.path.exists(fn):
        return sym, -1
    T, O, H, L, C, V = load15(sym)
    n = len(T)
    if n < (2000 if TFH == 4 else 700):
        return sym, 0
    atr = wilder(H, L, C, 14)
    e20, e50, e200 = ema(C, 20), ema(C, 50), ema(C, 200)
    bbm = np.convolve(C, np.ones(20) / 20, mode="full")[:n]; bbm[:19] = np.nan
    bbs = roll_std(C, 20)
    # the day's VWAP (UTC day), sigma of close - VWAP over 96 bars
    day = T // 86400
    tp = (H + L + C) / 3
    vw = np.empty(n); cv = 0.0; cpv = 0.0
    for i in range(n):
        if i == 0 or day[i] != day[i - 1]:
            cv = 0.0; cpv = 0.0
        cv += V[i]; cpv += tp[i] * V[i]
        vw[i] = cpv / cv if cv > 0 else C[i]
    vws = roll_std(C - vw, 96)
    hi96, lo96 = roll_minmax(H, L, 96)
    # ---- honest families on 1h bars ----
    NF = len(FAMS); lvl = np.full((NF, 2, n), np.nan); Wf = np.array([4] * NF, np.int64)
    for f_, dp in enumerate(DEP):
        lvl[f_, 0] = L - dp * atr; lvl[f_, 1] = H + dp * atr
    evs = []; SINCE = {}
    for f_ in range(NF):
        for si, side in ((0, 1), (1, -1)):
            fb = fills(L, H, lvl[f_, si], side, Wf[f_]); sn = bot_since(fb, Wf[f_]); SINCE[(f_, side)] = sn
            for j in np.flatnonzero(fb >= 0):
                if sn[j] < 0: continue
                d_ = (C[j] - lvl[f_, si, j]) * side / atr[j] if atr[j] > 0 else -1
                if d_ < 0.3 or d_ > 6.0: continue
                b = fb[j]; lv_ = lvl[f_, si, j]
                evs.append((j, f_, side, lv_, b, min(lv_, O[b]) if side > 0 else max(lv_, O[b])))
    evs.sort()
    I = np.array([x[0] for x in evs], np.int64); Fm = np.array([x[1] for x in evs], np.int64); S = np.array([x[2] for x in evs], np.int64)
    LV = np.array([x[3] for x in evs]); FB = np.array([x[4] for x in evs], np.int64); FP = np.array([x[5] for x in evs])

    m = len(I)
    if m == 0:
        return sym, 0
    R = np.zeros((len(EXITS), m), np.float32); K = np.zeros((len(EXITS), m), np.int16); W = np.zeros((len(EXITS), m), np.int8)
    for e, (tk, st, hd) in enumerate(EXITS):
        for j in range(m):
            fee_in = 0.0002
            r, k, w = simulate(O, H, L, C, int(FB[j]), int(S[j]), float(FP[j]), float(atr[I[j]]), tk, st, hd, fee_in, 24.0 / TFH)
            R[e, j] = r; K[e, j] = int(np.ceil((FB[j] - I[j] + k) * float(TFH))); W[e, j] = w
    # ---- features at the close of bar i ----
    # daily ATR% of the last closed day
    dmask = np.concatenate([[True], day[1:] != day[:-1]])
    dst = np.flatnonzero(dmask); den = np.concatenate([dst[1:], [n]])
    dH = np.maximum.reduceat(H, dst); dL = np.minimum.reduceat(L, dst); dC = C[den - 1]
    datr_d = wilder(dH, dL, dC, 14) / dC * 100
    dpi = np.searchsorted(day[dst], day) - 1
    datr = np.where(dpi >= 0, datr_d[np.maximum(dpi, 0)], np.nan)
    F = np.zeros((m, len(FNAMES)), np.float32)
    a = atr[I]; px = C[I]; s = S.astype(np.float64)
    F[:, 0] = Fm; F[:, 1] = S; F[:, 2] = a / px * 100; F[:, 3] = np.nan_to_num(datr[I])
    F[:, 4] = np.abs(LV - px) / a
    F[:, 5] = (T[I] // 3600) % 24; F[:, 6] = (day[I] + 3) % 7
    def ret(k):
        return s * (px / C[np.maximum(I - k, 0)] - 1) * 100
    F[:, 7] = ret(4); F[:, 8] = ret(16); F[:, 9] = ret(96)
    F[:, 10] = s * (px - e20[I]) / a; F[:, 11] = s * (px - e50[I]) / a; F[:, 12] = s * (px - e200[I]) / a
    F[:, 13] = s * (e50[I] - e50[np.maximum(I - 16, 0)]) / a
    r15 = rsi(C, 14); r60 = rsi(C, 56)
    F[:, 14] = s * (r15[I] - 50); F[:, 15] = s * (r60[I] - 50)
    F[:, 16] = np.nan_to_num(s * (px - bbm[I]) / np.where(bbs[I] > 0, bbs[I], np.nan))
    F[:, 17] = np.nan_to_num(s * (px - vw[I]) / np.where(vws[I] > 0, vws[I], np.nan))
    rg = hi96[I] - lo96[I]
    pos = np.where(rg > 0, (px - lo96[I]) / np.where(rg > 0, rg, 1), 0.5)
    F[:, 18] = np.where(S > 0, pos, 1 - pos)
    cvv = np.cumsum(np.insert(V, 0, 0.0))
    F[:, 19] = np.log((cvv[I + 1] - cvv[np.maximum(I - 3, 0)] + 1e-9) / ((cvv[I + 1] - cvv[np.maximum(I - 95, 0)]) / 24 + 1e-9))
    b = btc()
    bj = np.clip(np.searchsorted(b["T"], T[I], side="right") - 1, 96, len(b["T"]) - 1)
    F[:, 20] = s * (b["C"][bj] / b["C"][bj - 16] - 1) * 100; F[:, 21] = s * (b["C"][bj] / b["C"][bj - 96] - 1) * 100
    F[:, 22] = b["atr"][bj] / b["C"][bj] * 100
    up_w = H[I] - np.maximum(O[I], C[I]); dn_w = np.minimum(O[I], C[I]) - L[I]
    F[:, 23] = s * (dn_w - up_w) / a; F[:, 24] = (H[I] - L[I]) / a
    # bars since the previous event of the same family & side (crowding)
    since = np.array([SINCE[(int(Fm[j]), int(S[j]))][I[j]] for j in range(m)])
    F[:, 25] = np.log1p(since)
    F[:, 26] = ret(672)
    hi30 = np.array([H[max(0, i - 2880):i + 1].max() for i in I]); lo30 = np.array([L[max(0, i - 2880):i + 1].min() for i in I])
    p30 = np.where(hi30 > lo30, (px - lo30) / np.where(hi30 > lo30, hi30 - lo30, 1), 0.5)
    F[:, 27] = np.where(S > 0, p30, 1 - p30)
    np.savez_compressed(fn, t=T[I], i=I, fam=Fm, side=S, R=R, K=K, W=W, F=F)
    return sym, m


if __name__ == "__main__":
    import json, multiprocessing as mp
    os.makedirs(OUT, exist_ok=True)
    syms = ARGS or [l.strip() for l in open(os.environ.get("COINS", "coins127.txt")) if l.strip()]
    t0 = time.time()
    if len(syms) == 1:
        print(run(syms[0]), round(time.time() - t0, 1))
    else:
        with mp.Pool(4) as pool:
            for k, (s_, m) in enumerate(pool.imap_unordered(run, syms)):
                if k % 20 == 0: print(k, s_, m, round(time.time() - t0), flush=True)
    print("done", round(time.time() - t0))
