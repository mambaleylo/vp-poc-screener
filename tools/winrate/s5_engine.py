"""5m version (bars built from the Binance 1m klines of 40 coins, 2024-10 .. 2026-09). Win-rate hunt (the user: "главная цель только винрейт и количество сделок… хоть минутный тайм фрейм… rr не важен, главное
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

FAMS = ["deep2", "deep3", "bb", "ema_pb", "vwap2", "sweep"]
EXITS = ((0.5, 2.0, 48), (1.0, 2.0, 96), (0.3, 1.5, 24), (0.5, 1.0, 48), (0.2, 2.0, 24))
FNAMES = ["fam", "side", "atrp", "datr", "depth", "hour", "dow", "r1h", "r4h", "r24h", "e20", "e50", "e200", "sl50", "rsi", "rsi4",
          "bbz", "vwz", "pos96", "volr", "b4h", "b24h", "batr", "wick", "rng", "since", "r7d", "dpos30"]
OUT = f"{D}/s5"


def load15(sym):
    """5m bars from the 1m npz"""
    z = np.load(f"{D}/data/1mz/{sym}.npz")
    t = z["t"]; g = t // 300
    st = np.flatnonzero(np.concatenate([[True], g[1:] != g[:-1]]))
    en = np.concatenate([st[1:], [len(t)]])
    return (g[st] * 300).astype(np.int64), z["o"][st], np.maximum.reduceat(z["h"], st), np.minimum.reduceat(z["l"], st), z["c"][en - 1], np.add.reduceat(z["qv"].astype(np.float64), st)


@njit(cache=True)
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


@njit(cache=True)
def ema(x, n):
    out = np.empty(len(x)); k = 2.0 / (n + 1); e = x[0]
    for i in range(len(x)):
        e = x[i] if i == 0 else e + k * (x[i] - e); out[i] = e
    return out


@njit(cache=True)
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


@njit(cache=True)
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


@njit(cache=True)
def roll_minmax(H, L, n):
    """max high / min low of the n bars BEFORE i"""
    hi = np.full(len(H), np.nan); lo = np.full(len(H), np.nan)
    for i in range(n, len(H)):
        hi[i] = H[i - n:i].max(); lo[i] = L[i - n:i].min()
    return hi, lo


@njit(cache=True)
def simulate(O, H, L, C, f, side, fill, atr, take, stop, hold, fee_in):
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
    fees = (fee_in + fee_out + 0.0003 * (k + 1) / 288.0) * fill
    return (side * (ex - fill) - fees) / risk, k + 1, win


@njit(cache=True)
def find_events(O, H, L, C, atr, e20, e50, e200, bbm, bbs, vw, vws, hi96, lo96):
    """(i, fam, side, level, fill bar, fill price); one order per family & side alive at a time"""
    n = len(C)
    ev_i = []; ev_f = []; ev_s = []; ev_lv = []; ev_fb = []; ev_fp = []
    busy = np.zeros((6, 2), np.int64)
    for i in range(300, n - 1):
        a = atr[i]
        if not (a > 0):
            continue
        for fam in range(6):
            for si in range(2):
                side = 1 if si == 0 else -1
                if busy[fam, si] > i:
                    continue
                lv = np.nan; W = 1; market = False
                if fam == 0:
                    lv = C[i] - side * 2.0 * a; W = 4
                elif fam == 1:
                    lv = C[i] - side * 3.0 * a; W = 4
                elif fam == 2:
                    if bbs[i] == bbs[i]:
                        lv = bbm[i] - side * 2.5 * bbs[i]
                        if (side > 0 and C[i] <= lv) or (side < 0 and C[i] >= lv):
                            lv = np.nan
                elif fam == 3:
                    if side > 0 and e50[i] > e200[i] and C[i] > e20[i]:
                        lv = e20[i]; W = 2
                    elif side < 0 and e50[i] < e200[i] and C[i] < e20[i]:
                        lv = e20[i]; W = 2
                elif fam == 4:
                    if vws[i] == vws[i] and vws[i] > 0:
                        lv = vw[i] - side * 2.0 * vws[i]
                        if (side > 0 and C[i] <= lv) or (side < 0 and C[i] >= lv):
                            lv = np.nan
                elif fam == 5:
                    if lo96[i] == lo96[i]:
                        if side > 0 and L[i] < lo96[i] and C[i] > lo96[i]:
                            market = True
                        elif side < 0 and H[i] > hi96[i] and C[i] < hi96[i]:
                            market = True
                if market:
                    ev_i.append(i); ev_f.append(fam); ev_s.append(side); ev_lv.append(O[i + 1]); ev_fb.append(i + 1); ev_fp.append(O[i + 1])
                    busy[fam, si] = i + 4
                    continue
                if not (lv == lv):
                    continue
                for w in range(1, W + 1):
                    b = i + w
                    if b >= n:
                        break
                    if side > 0 and L[b] <= lv:
                        ev_i.append(i); ev_f.append(fam); ev_s.append(side); ev_lv.append(lv); ev_fb.append(b); ev_fp.append(min(lv, O[b]))
                        busy[fam, si] = b + 1
                        break
                    if side < 0 and H[b] >= lv:
                        ev_i.append(i); ev_f.append(fam); ev_s.append(side); ev_lv.append(lv); ev_fb.append(b); ev_fp.append(max(lv, O[b]))
                        busy[fam, si] = b + 1
                        break
    return (np.array(ev_i), np.array(ev_f), np.array(ev_s), np.array(ev_lv), np.array(ev_fb), np.array(ev_fp))


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
    if n < 2000:
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
    vws = roll_std(C - vw, 288)
    hi96, lo96 = roll_minmax(H, L, 288)
    I, Fm, S, LV, FB, FP = find_events(O, H, L, C, atr, e20, e50, e200, bbm, bbs, vw, vws, hi96, lo96)
    m = len(I)
    if m == 0:
        return sym, 0
    R = np.zeros((len(EXITS), m), np.float32); K = np.zeros((len(EXITS), m), np.int16); W = np.zeros((len(EXITS), m), np.int8)
    for e, (tk, st, hd) in enumerate(EXITS):
        for j in range(m):
            fee_in = 0.0005 if Fm[j] == 5 else 0.0002
            r, k, w = simulate(O, H, L, C, int(FB[j]), int(S[j]), float(FP[j]), float(atr[I[j]]), tk, st, hd, fee_in)
            R[e, j] = r; K[e, j] = int(np.ceil((FB[j] - I[j] + k) / 12.0)); W[e, j] = w
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
    F[:, 7] = ret(12); F[:, 8] = ret(48); F[:, 9] = ret(288)
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
    F[:, 19] = np.log((cvv[I + 1] - cvv[np.maximum(I - 11, 0)] + 1e-9) / ((cvv[I + 1] - cvv[np.maximum(I - 287, 0)]) / 24 + 1e-9))
    b = btc()
    bj = np.clip(np.searchsorted(b["T"], T[I], side="right") - 1, 288, len(b["T"]) - 1)
    F[:, 20] = s * (b["C"][bj] / b["C"][bj - 48] - 1) * 100; F[:, 21] = s * (b["C"][bj] / b["C"][bj - 288] - 1) * 100
    F[:, 22] = b["atr"][bj] / b["C"][bj] * 100
    up_w = H[I] - np.maximum(O[I], C[I]); dn_w = np.minimum(O[I], C[I]) - L[I]
    F[:, 23] = s * (dn_w - up_w) / a; F[:, 24] = (H[I] - L[I]) / a
    # bars since the previous event of the same family & side (crowding)
    since = np.full(m, 999.0); last = {}
    for j in range(m):
        key = (int(Fm[j]), int(S[j]))
        if key in last: since[j] = min(999.0, float(I[j] - last[key]))
        last[key] = I[j]
    F[:, 25] = np.log1p(since)
    F[:, 26] = ret(2016)
    hi30 = np.array([H[max(0, i - 8640):i + 1].max() for i in I]); lo30 = np.array([L[max(0, i - 8640):i + 1].min() for i in I])
    p30 = np.where(hi30 > lo30, (px - lo30) / np.where(hi30 > lo30, hi30 - lo30, 1), 0.5)
    F[:, 27] = np.where(S > 0, p30, 1 - p30)
    np.savez_compressed(fn, t=T[I], i=I, fam=Fm, side=S, R=R, K=K, W=W, F=F)
    return sym, m


if __name__ == "__main__":
    import json, multiprocessing as mp
    os.makedirs(OUT, exist_ok=True)
    syms = ARGS or sorted(f[:-4] for f in os.listdir(f"{D}/data/1mz") if f.endswith(".npz"))
    t0 = time.time()
    if len(syms) == 1:
        print(run(syms[0]), round(time.time() - t0, 1))
    else:
        with mp.Pool(4) as pool:
            for k, (s_, m) in enumerate(pool.imap_unordered(run, syms)):
                if k % 20 == 0: print(k, s_, m, round(time.time() - t0), flush=True)
    print("done", round(time.time() - t0))
