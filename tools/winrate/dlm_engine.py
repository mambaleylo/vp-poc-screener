"""⚡ engine v2 (rebuilt 2026-11 after the research folder was lost): the bot's own ⚡ limits over a coin's whole history,
vectorized — dlm_candidates4's 33 features (the same formulas; the bot computes them on its last 3000 4h / 4500 2h bars, the
indicators here on the whole history: the same values once the window's start has decayed — t_dlm_engine.py checks it
against the bot's function), dlm_since, the order's fill on the 1h candles (_dlm_hit: the first 1h candle of the order's 4
bars reaching the level; the fill = the level or the chart bar's open if it opened through it) and the trade's walk
(_dlm_walk_1h / _dlm_r_h: the emergency stop 3 ATR first in an hour, the take 1.1 ATR not in the touch hour, the stop at
the close of the chart's candle beyond 2 ATR, out after 32 bars; R per the 2 ATR stop with the fees and the funding).
Only the orders that fill are kept (the pool and the training are made of them).
Candles: LABDATA (default /home/user/vp-lab-store/data/1h/<SYM>.csv.gz — the lab-store branch)."""
import os, numpy as np
from numba import njit

DATA = os.environ.get("LABDATA", "/home/user/vp-lab-store/data/1h")
STREAMS = {"wick4h": dict(hh=4, nb=3000, wick=True, depth=1.0, fam=2.0, ch=4),
           "close2h": dict(hh=2, nb=4500, wick=False, depth=2.0, fam=0.0, ch=2),
           # the other charts tried as a third stream (the user: "какие таймфремы для лимиток ещё можно попробовать"): the 4h wick
           # rule on the 4h grid shifted by 2 h (02-06, 06-10 … UTC: "off" hours), on 3h / 6h / 8h bars; ~500 days of the bot's window
           "wick4h_o2": dict(hh=4, off=2, nb=3000, wick=True, depth=1.0, fam=2.0, ch=4),
           "wick4h_o1": dict(hh=4, off=1, nb=3000, wick=True, depth=1.0, fam=2.0, ch=4),
           "wick4h_o3": dict(hh=4, off=3, nb=3000, wick=True, depth=1.0, fam=2.0, ch=4),
           "wick3h": dict(hh=3, nb=4000, wick=True, depth=1.0, fam=2.0, ch=3),
           "wick6h": dict(hh=6, nb=2000, wick=True, depth=1.0, fam=2.0, ch=6),
           "wick8h": dict(hh=8, nb=1500, wick=True, depth=1.0, fam=2.0, ch=8, minb=1500)}
ALIVE, HOLD, TAKE, SOFT, HARD = 4, 32, 1.1, 2.0, 3.0
DMIN, DMAX, MIN_BARS, MIN_SL_FRAC = 0.3, 6.0, 2000, 0.001
FEE_IN, FEE_TAKE, FEE_OUT, FUND = 0.0002, 0.0002, 0.0005, 0.0003
NF = 33


def shift(h1, off):
    """the 1h arrays with the times moved back by `off` hours (a shifted chart grid: its bars start at off, off + hh …)"""
    return h1 if not off else (h1[0] - off * 3600,) + tuple(h1[1:])


def walk(stream, h1, t0s, sides, lvs, atrs, take=None, soft=None, hard=None, hold=None):
    """fill_walk on the stream's own grid (a shifted one too) -> its outputs in real times"""
    p = STREAMS[stream]; off = p.get("off", 0) * 3600; T1, O1, H1, L1, C1, V1 = h1
    fl, t1h, fill, R, kind, tout = fill_walk(T1 - off, O1, H1, L1, C1, np.asarray(t0s) - off, np.asarray(sides, np.int64), lvs, atrs, p["hh"] * 3600,
                                             p["ch"], ALIVE, HOLD if hold is None else hold, TAKE if take is None else take, SOFT if soft is None else soft,
                                             HARD if hard is None else hard, FEE_IN, FEE_TAKE, FEE_OUT, FUND)
    return fl, np.where(fl, t1h + off, 0), fill, R, kind, np.where(fl, tout + off, 0)


def load1h(bsym):
    fn = os.path.join(DATA, f"{bsym}.csv.gz")
    if not os.path.exists(fn):
        fn = os.path.join(DATA, f"{bsym}.csv")
    a = np.loadtxt(fn, delimiter=",", ndmin=2)
    t = a[:, 0].astype(np.int64)
    k = np.concatenate([[True], np.diff(t) > 0])
    a = a[k]
    return a[:, 0].astype(np.int64), a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5]


def chart(T, O, H, L, C, V, hh):
    """the chart's bars from the 1h ones (UTC blocks, the complete ones — as Binance's own when no hour is missing)"""
    blk = T // (hh * 3600)
    st = np.concatenate([[0], np.flatnonzero(blk[1:] != blk[:-1]) + 1]); en = np.concatenate([st[1:], [len(T)]])
    full = (en - st) == hh
    st, en = st[full], en[full]
    return (blk[st] * hh * 3600, O[st], np.array([H[s:e].max() for s, e in zip(st, en)]),
            np.array([L[s:e].min() for s, e in zip(st, en)]), C[en - 1], np.array([V[s:e].sum() for s, e in zip(st, en)]))


@njit(cache=True)
def wilder(H, L, C, n=14):
    out = np.full(len(C), np.nan)
    if len(C) <= n:
        return out
    s = 0.0
    for i in range(n):
        s += (H[i] - L[i]) if i == 0 else max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1]))
    a = s / n; out[n - 1] = a
    for i in range(n, len(C)):
        a = (a * (n - 1) + max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1]))) / n
        out[i] = a
    return out


@njit(cache=True)
def ema(x, n):
    out = np.empty(len(x)); k = 2.0 / (n + 1); e = x[0]
    for i in range(len(x)):
        e = x[i] if i == 0 else e + k * (x[i] - e)
        out[i] = e
    return out


@njit(cache=True)
def rsi(C, n):
    out = np.full(len(C), 50.0); au = 0.0; ad = 0.0
    for i in range(1, len(C)):
        d = C[i] - C[i - 1]
        u = d if d > 0 else 0.0; dn = -d if d < 0 else 0.0
        if i <= n:
            au += u / n; ad += dn / n
        else:
            au = (au * (n - 1) + u) / n; ad = (ad * (n - 1) + dn) / n
        if i >= n:
            out[i] = 100 - 100 / (1 + au / ad) if ad > 0 else 100.0
    return out


@njit(cache=True)
def since_all(H, L, C, atr, side, depth, wick, nb, alive=4, back=1000):
    """dlm_since for every bar i as the bot computes it on its window (the last nb bars): -1 = None"""
    n = len(C); out = np.full(n, -2, np.int64)
    for i0 in range(n):
        w0 = max(0, i0 - nb + 1)
        last = -1; busy = -1
        for j in range(max(w0 + 300, i0 - back), i0):
            if busy > j or not (atr[j] > 0):
                continue
            lv = ((L[j] if side > 0 else H[j]) if wick else C[j]) - side * depth * atr[j]
            for b in range(j + 1, min(j + alive, i0) + 1):
                if (L[b] <= lv) if side > 0 else (H[b] >= lv):
                    last = j; busy = b + 1
                    break
        if busy > i0:
            out[i0] = -1
        else:
            out[i0] = min(999, i0 - last) if last >= 0 else 999
    return out


def rolling_max(x, w):   # max of x[i-w+1 .. i]
    from numpy.lib.stride_tricks import sliding_window_view
    out = np.full(len(x), np.nan)
    if len(x) >= w:
        out[w - 1:] = sliding_window_view(x, w).max(axis=1)
    return out


def rolling_min(x, w):
    from numpy.lib.stride_tricks import sliding_window_view
    out = np.full(len(x), np.nan)
    if len(x) >= w:
        out[w - 1:] = sliding_window_view(x, w).min(axis=1)
    return out


def daily(T, H, L, C):
    """the UTC days of the chart's bars: (day numbers, high, low, close)"""
    d = T // 86400
    st = np.concatenate([[0], np.flatnonzero(d[1:] != d[:-1]) + 1]); en = np.concatenate([st[1:], [len(d)]])
    return d[st], np.array([H[s:e].max() for s, e in zip(st, en)]), np.array([L[s:e].min() for s, e in zip(st, en)]), C[en - 1]


def btc_ctx(stream):
    """BTC's chart bars and its daily context for the stream (the same for every coin)"""
    p = STREAMS[stream]
    T1, O1, H1, L1, C1, V1 = shift(load1h("BTCUSDT"), p.get("off", 0))
    bT, bO, bH, bL, bC, bV = chart(T1, O1, H1, L1, C1, V1, p["hh"])
    batr = wilder(bH, bL, bC)
    dd, dH, dL, dC = daily(bT, bH, bL, bC)
    return dict(T=bT, C=bC, atr=batr, dd=dd, dC=dC, de50=ema(dC, 50))


def features(bsym, stream, B=None, h1=None):
    """the coin's ⚡ limits of the stream that pass the bot's filters: arrays of the bar (its open time), side, the level,
    the ATR, the 33 features"""
    p = STREAMS[stream]; hh, nb = p["hh"], p["nb"]; bs = hh * 3600; off = p.get("off", 0); minb = p.get("minb", MIN_BARS)
    T1, O1, H1, L1, C1, V1 = shift(h1 if h1 is not None else load1h(bsym), off)   # a shifted grid: everything on it, "t" back at the end
    T, O, H, L, C, V = chart(T1, O1, H1, L1, C1, V1, hh)
    n = len(C)
    if n < minb + 1:
        return None
    B = B or btc_ctx(stream)
    atr = wilder(H, L, C)
    e20, e50, e200 = ema(C, 20), ema(C, 50), ema(C, 200)
    r15, r60 = rsi(C, 14), rsi(C, 56)
    # Bollinger 20 (population), the daily-anchored VWAP and its distance's sd over 96 bars
    from numpy.lib.stride_tricks import sliding_window_view
    bbm = np.full(n, np.nan); bbs = np.full(n, np.nan)
    w = sliding_window_view(C, 20); bbm[19:] = w.mean(axis=1); bbs[19:] = np.sqrt(np.maximum((w * w).mean(axis=1) - bbm[19:] ** 2, 0.0))
    day = T // 86400
    tp = (H + L + C) / 3 * V
    vw = np.empty(n); cv = cpv = 0.0
    for k in range(n):
        if k == 0 or day[k] != day[k - 1]:
            cv = cpv = 0.0
        cv += V[k]; cpv += tp[k]
        vw[k] = cpv / cv if cv > 0 else C[k]
    dv = C - vw
    vm = np.full(n, np.nan); vs = np.full(n, np.nan)
    w = sliding_window_view(dv, 96); vm[95:] = w.mean(axis=1); vs[95:] = np.sqrt(np.maximum((w * w).mean(axis=1) - vm[95:] ** 2, 0.0))
    hi96 = np.full(n, np.nan); lo96 = np.full(n, np.nan)
    hi96[96:] = rolling_max(H, 96)[95:-1]; lo96[96:] = rolling_min(L, 96)[95:-1]   # H[i-96:i]
    cV = np.concatenate([[0.0], np.cumsum(V)])
    v4 = np.full(n, np.nan); v96 = np.full(n, np.nan)
    v4[3:] = cV[4:] - cV[:-4]; v96[95:] = cV[96:] - cV[:-96]
    rm = rolling_max(H, 2881); hi30 = np.where(np.isnan(rm), np.maximum.accumulate(H), rm)   # over [i-2880, i]
    rn = rolling_min(L, 2881); lo30 = np.where(np.isnan(rn), np.minimum.accumulate(L), rn)
    # the daily context: the last closed UTC day before the bar's day
    dd, dH, dL, dC = daily(T, H, L, C)
    datr_d = wilder(dH, dL, dC); de20_d, de50_d, dr14_d = ema(dC, 20), ema(dC, 50), rsi(dC, 14)
    dhi_d, dlo_d = rolling_max(dH, 20), rolling_min(dL, 20)
    kd = np.searchsorted(dd, day, side="left") - 1          # the last day < the bar's day
    # the days in the bot's window before the bar's day (>= 15 needed)
    w0 = np.maximum(0, np.arange(n) - nb + 1)
    kd0 = np.searchsorted(dd, day[w0], side="left")
    ndays = kd - kd0 + 1
    # BTC
    bj = np.searchsorted(B["T"], T, side="right") - 1
    bkd = np.searchsorted(B["dd"], day, side="left") - 1
    ups = H - np.maximum(O, C); dns = np.minimum(O, C) - L
    out = {k: [] for k in ("i", "t", "side", "lv", "atr", "f")}
    idx = np.arange(n)
    ok = (idx >= minb - 1) & (atr > 0) & (ndays >= 15) & (kd >= 0) & (bj >= 96) & (bkd >= 0) & np.isfinite(vs) & (idx >= 96)
    sinces = {s: since_all(H, L, C, atr, s, p["depth"], p["wick"], nb) for s in (1, -1)}
    for s in (1, -1):
        sf = float(s)
        lv = ((L if s > 0 else H) if p["wick"] else C) - s * p["depth"] * atr
        dep = np.abs(lv - C) / atr
        sn = sinces[s]
        m = ok & (dep >= DMIN) & (dep <= DMAX) & (sn >= 0) & ~(SOFT * atr < np.abs(lv) * MIN_SL_FRAC)
        ii = np.flatnonzero(m)
        if not len(ii):
            continue
        a = atr[ii]; px = C[ii]
        def ret(k):
            return sf * (px / C[np.maximum(ii - k, w0[ii])] - 1) * 100
        rg = hi96[ii] - lo96[ii]; pos = np.where(rg > 0, (px - lo96[ii]) / np.where(rg > 0, rg, 1), 0.5)
        r30 = hi30[ii] - lo30[ii]; p30 = np.where(r30 > 0, (px - lo30[ii]) / np.where(r30 > 0, r30, 1), 0.5)
        k_ = kd[ii]; dat = datr_d[k_]
        bjj = bj[ii]; bk = bkd[ii]
        dr = dhi_d[k_] - dlo_d[k_]; dp = np.where(dr > 0, (px - dlo_d[k_]) / np.where(dr > 0, dr, 1), 0.5)
        datr = np.where(dat > 0, dat / dC[k_] * 100, 0.0)
        safe_dat = np.where(dat > 0, dat, 1.0)
        F = np.column_stack([
            np.full(len(ii), p["fam"]), np.full(len(ii), sf), a / px * 100, datr, dep[ii], ((T[ii] // 3600) % 24).astype(float),
            ((day[ii] + 3) % 7).astype(float), ret(4), ret(16), ret(96),
            sf * (px - e20[ii]) / a, sf * (px - e50[ii]) / a, sf * (px - e200[ii]) / a, sf * (e50[ii] - e50[np.maximum(ii - 16, 0)]) / a,
            sf * (r15[ii] - 50), sf * (r60[ii] - 50), np.where(bbs[ii] > 0, sf * (px - bbm[ii]) / np.where(bbs[ii] > 0, bbs[ii], 1), 0.0),
            np.where(vs[ii] > 0, sf * (px - vw[ii]) / np.where(vs[ii] > 0, vs[ii], 1), 0.0),
            pos if s > 0 else 1 - pos, np.log((v4[ii] + 1e-9) / (v96[ii] / 24 + 1e-9)),
            sf * (B["C"][bjj] / B["C"][bjj - 16] - 1) * 100, sf * (B["C"][bjj] / B["C"][bjj - 96] - 1) * 100,
            np.where(B["atr"][bjj] > 0, B["atr"][bjj] / B["C"][bjj] * 100, 0.0), sf * (dns[ii] - ups[ii]) / a, (H[ii] - L[ii]) / a,
            np.log1p(sn[ii].astype(float)), ret(672), p30 if s > 0 else 1 - p30,
            np.where(dat > 0, sf * (px - de20_d[k_]) / safe_dat, 0.0), np.where(dat > 0, sf * (px - de50_d[k_]) / safe_dat, 0.0),
            sf * (dr14_d[k_] - 50), dp if s > 0 else 1 - dp, sf * (B["dC"][bk] / B["de50"][bk] - 1) * 100])
        out["i"].append(ii); out["t"].append(T[ii]); out["side"].append(np.full(len(ii), s)); out["lv"].append(lv[ii]); out["atr"].append(a); out["f"].append(F)
    if not out["i"]:
        return None
    r = {k: np.concatenate(v) for k, v in out.items()}
    o = np.argsort(r["t"], kind="stable"); r["t"] = r["t"] + off * 3600
    return {k: v[o] for k, v in r.items()} | {"bs": bs, "stream": stream}


@njit(cache=True)
def fill_walk(T1, O1, H1, L1, C1, t0s, sides, lvs, atrs, bs, ch, alive, hold, take, soft, hard, fee_in, fee_take, fee_out, fund):
    """each order alive from t0 (its scan, the bar's close) for `alive` bars: its touch on the 1h candles and the trade
    -> (filled, t1h, fill, R, kind 1 take / 0 emergency / 4 close stop / 3 time, t_out)"""
    m = len(t0s)
    filled = np.zeros(m, np.bool_); t1h = np.zeros(m, np.int64); fills = np.zeros(m); R = np.full(m, np.nan)
    kinds = np.full(m, -1, np.int64); tout = np.zeros(m, np.int64)
    for k in range(m):
        s = sides[k]; lv = lvs[k]; a = atrs[k]; t0 = t0s[k]; until = t0 + alive * bs
        i = np.searchsorted(T1, t0)
        hit = -1
        while i < len(T1) and T1[i] < until:
            if (L1[i] <= lv) if s > 0 else (H1[i] >= lv):
                hit = i
                break
            i += 1
        if hit < 0:
            continue
        fb = T1[hit] // bs * bs
        j = np.searchsorted(T1, fb)
        fo = O1[j] if (j < len(T1) and T1[j] == fb) else O1[hit]
        e = min(lv, fo) if s > 0 else max(lv, fo)
        filled[k] = True; t1h[k] = T1[hit]; fills[k] = e
        sl = e - s * soft * a; hsl = e - s * hard * a; tp = e + s * take * a; risk = soft * a
        end = fb + hold * bs
        q = 0; b = hit; res = -1; ex = 0.0
        while b < len(T1) and T1[b] < end:
            if (L1[b] <= hsl) if s > 0 else (H1[b] >= hsl):
                gap = q > 0 and ((O1[b] <= hsl) if s > 0 else (O1[b] >= hsl))
                ex = O1[b] if gap else hsl; res = 0
                break
            if q > 0 and ((H1[b] >= tp) if s > 0 else (L1[b] <= tp)):
                ex = tp; res = 1
                break
            if (T1[b] + 3600) % (ch * 3600) == 0 and ((C1[b] <= sl) if s > 0 else (C1[b] >= sl)):
                ex = C1[b]; res = 4
                break
            q += 1; b += 1
        if res < 0:
            if b > hit and T1[b - 1] + 3600 >= end:
                b -= 1; ex = C1[b]; res = 3; q = b - hit
            else:
                filled[k] = False   # the data ends before the trade does
                continue
        fee = (fee_in + (fee_take if res == 1 else fee_out) + fund * (q + 1) / 24) * e
        R[k] = (s * (ex - e) - fee) / risk; kinds[k] = res; tout[k] = T1[b] + 3600
    return filled, t1h, fills, R, kinds, tout


def coin(bsym, stream, B=None):
    """the coin's filled ⚡ orders of the stream with their trades"""
    h1 = load1h(bsym)
    ev = features(bsym, stream, B, h1)
    if ev is None:
        return None
    p = STREAMS[stream]; bs = ev["bs"]
    fl, t1h, fill, R, kind, tout = walk(stream, h1, ev["t"] + bs, ev["side"], ev["lv"], ev["atr"])
    keep = fl
    return {"t": ev["t"][keep] + bs, "side": ev["side"][keep].astype(np.int8), "lv": ev["lv"][keep], "atr": ev["atr"][keep],
            "F": ev["f"][keep].astype(np.float32), "t1h": t1h[keep], "fill": fill[keep], "R": R[keep].astype(np.float32),
            "kind": kind[keep].astype(np.int8), "tout": tout[keep], "n_orders": int(len(ev["t"]))}
