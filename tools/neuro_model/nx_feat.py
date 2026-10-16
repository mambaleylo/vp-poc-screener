"""Neuro v3 features — pure Python, causal, the same code in the research and the bot.
nx_series(...) -> (names, rows): rows[i] = features known at the CLOSE of 1h bar i (entry at bar i+1's open)."""
import math, bisect

def _ema(v, n):
    out, k, e = [None] * len(v), 2 / (n + 1), None
    for i, x in enumerate(v):
        e = x if e is None else e + k * (x - e)
        out[i] = e if i >= n - 1 else None
    return out

def _sma(v, n):
    out, s = [None] * len(v), 0.0
    for i, x in enumerate(v):
        s += x
        if i >= n:
            s -= v[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out

def _rsi(c, n=14):
    out = [None] * len(c)
    g = l = 0.0
    for i in range(1, len(c)):
        d = c[i] - c[i - 1]
        up, dn = max(d, 0.0), max(-d, 0.0)
        if i <= n:
            g += up / n
            l += dn / n
            if i == n:
                out[i] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
        else:
            g = (g * (n - 1) + up) / n
            l = (l * (n - 1) + dn) / n
            out[i] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
    return out

def _tr(h, l, c):
    return [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]

def _wilder(v, n):
    out, s = [None] * len(v), None
    for i, x in enumerate(v):
        if i < n - 1:
            continue
        if s is None:
            s = sum(v[i - n + 1:i + 1]) / n
        else:
            s = (s * (n - 1) + x) / n
        out[i] = s
    return out

def _hh(v, n):
    """rolling max over the last n (incl. i)"""
    from collections import deque
    out, dq = [None] * len(v), deque()
    for i, x in enumerate(v):
        while dq and v[dq[-1]] <= x:
            dq.pop()
        dq.append(i)
        if dq[0] <= i - n:
            dq.popleft()
        out[i] = v[dq[0]]
    return out

def _ll(v, n):
    return [-x for x in _hh([-y for y in v], n)]

def _std(v, n):
    out, s, s2 = [None] * len(v), 0.0, 0.0
    for i, x in enumerate(v):
        s += x
        s2 += x * x
        if i >= n:
            s -= v[i - n]
            s2 -= v[i - n] ** 2
        if i >= n - 1:
            out[i] = math.sqrt(max(0.0, s2 / n - (s / n) ** 2))
    return out

def _tf_ind(bars):
    """a higher chart's indicators per closed bar"""
    C = [b["close"] for b in bars]
    H = [b["high"] for b in bars]
    L = [b["low"] for b in bars]
    atr = _wilder(_tr(H, L, C), 14) if bars else []
    e12, e26 = _ema(C, 12), _ema(C, 26)
    macd = [a - b if a is not None and b is not None else None for a, b in zip(e12, e26)]
    sig = _ema([m if m is not None else 0.0 for m in macd], 9)
    ll14, hh14 = _ll(L, 14), _hh(H, 14)
    return {"t_end": None, "C": C, "atr": atr, "rsi": _rsi(C, 14), "e20": _ema(C, 20), "e50": _ema(C, 50), "e200": _ema(C, 200),
            "macd": macd, "sig": sig, "ll14": ll14, "hh14": hh14, "hh30": _hh(H, 30), "ll30": _ll(L, 30),
            "hh365": _hh(H, 365), "ll365": _ll(L, 365)}

def _cl(x, a=-50.0, b=50.0):
    return a if x < a else (b if x > b else x)

NAMES = None

def nx_series(h1, h4, d1, w1, btc, eth, funding, start=0):
    """h1/h4/d1/w1: closed candles (dicts) oldest first; btc, eth: their closed 1h candles; funding: [(t, rate)].
    Rows from index `start` (the earlier bars still warm the indicators up)."""
    n = len(h1)
    T = [b["time"] for b in h1]
    O = [b["open"] for b in h1]
    H = [b["high"] for b in h1]
    L = [b["low"] for b in h1]
    C = [b["close"] for b in h1]
    V = [b.get("volume") or 0.0 for b in h1]
    tr = _tr(H, L, C)
    atr = _wilder(tr, 14)
    atr100 = _sma(tr, 100)
    em = {k: _ema(C, k) for k in (9, 20, 50, 100, 200)}
    e12, e26 = _ema(C, 12), _ema(C, 26)
    macd = [a - b if a is not None and b is not None else 0.0 for a, b in zip(e12, e26)]
    msig = _ema(macd, 9)
    rsi14, rsi7 = _rsi(C, 14), _rsi(C, 7)
    hh14, ll14 = _hh(H, 14), _ll(L, 14)
    hh24, ll24 = _hh(H, 24), _ll(L, 24)
    hh168, ll168 = _hh(H, 168), _ll(L, 168)
    hh720, ll720 = _hh(H, 720), _ll(L, 720)
    sma20, sd20 = _sma(C, 20), _std(C, 20)
    tp = [(h + l + c) / 3 for h, l, c in zip(H, L, C)]
    tp_sma, tp_sd = _sma(tp, 20), None
    md = [None] * n
    for i in range(19, n):
        m_ = tp_sma[i]
        md[i] = sum(abs(x - m_) for x in tp[i - 19:i + 1]) / 20
    pv = [p * v for p, v in zip(tp, V)]
    s_pv, s_v = _sma(pv, 20), _sma(V, 20)
    # ADX
    pdm = [0.0] + [max(H[i] - H[i - 1], 0.0) if H[i] - H[i - 1] > L[i - 1] - L[i] else 0.0 for i in range(1, n)]
    ndm = [0.0] + [max(L[i - 1] - L[i], 0.0) if L[i - 1] - L[i] > H[i] - H[i - 1] else 0.0 for i in range(1, n)]
    trw, pw, nw = _wilder(tr, 14), _wilder(pdm, 14), _wilder(ndm, 14)
    pdi = [100 * p / t if p is not None and t else None for p, t in zip(pw, trw)]
    ndi = [100 * p / t if p is not None and t else None for p, t in zip(nw, trw)]
    dx = [100 * abs(a - b) / (a + b) if a is not None and b is not None and (a + b) > 0 else 0.0 for a, b in zip(pdi, ndi)]
    adx = _wilder(dx, 14)
    # supertrend (10, 3)
    st_dir, st_line = [0] * n, [None] * n
    at10 = _wilder(tr, 10)
    fu = fl = None
    d_ = 1
    for i in range(n):
        if at10[i] is None:
            continue
        mid = (H[i] + L[i]) / 2
        bu, bl = mid + 3 * at10[i], mid - 3 * at10[i]
        fu = bu if fu is None or bu < fu or C[i - 1] > fu else fu
        fl = bl if fl is None or bl > fl or C[i - 1] < fl else fl
        if d_ > 0 and C[i] < fl:
            d_ = -1
        elif d_ < 0 and C[i] > fu:
            d_ = 1
        st_dir[i], st_line[i] = d_, (fl if d_ > 0 else fu)
    # ichimoku
    tenkan = [(a + b) / 2 for a, b in zip(_hh(H, 9), _ll(L, 9))]
    kijun = [(a + b) / 2 for a, b in zip(_hh(H, 26), _ll(L, 26))]
    sb = [(a + b) / 2 for a, b in zip(_hh(H, 52), _ll(L, 52))]
    # OBV
    obv = [0.0] * n
    for i in range(1, n):
        obv[i] = obv[i - 1] + (V[i] if C[i] > C[i - 1] else (-V[i] if C[i] < C[i - 1] else 0.0))
    lv = [math.log(v + 1e-9) for v in V]
    lv_m, lv_s = _sma(lv, 168), _std(lv, 168)
    lr = [0.0] + [math.log(C[i] / C[i - 1]) if C[i - 1] > 0 else 0.0 for i in range(1, n)]
    rv24, rv168 = _std(lr, 24), _std(lr, 168)
    # chop
    s_tr14 = _sma(tr, 14)
    # higher charts
    def tf_index(bars, sec):
        ends = [b["time"] + sec for b in bars]
        return [bisect.bisect_right(ends, T[i] + 3600) - 1 for i in range(n)]
    i4, idd = tf_index(h4, 4 * 3600), tf_index(d1, 86400)
    I4, ID = _tf_ind(h4), _tf_ind(d1)
    wend = []
    for b in w1:
        y = b["time"]
        wend.append(y + 7 * 86400)
    iw = [bisect.bisect_right(wend, T[i] + 3600) - 1 for i in range(n)]
    wC = [b["close"] for b in w1]
    we21 = _ema(wC, 21)
    # BTC / ETH by time
    bT = [b["time"] for b in btc]
    bC = [b["close"] for b in btc]
    b_rsi = _rsi(bC, 14)
    b_e50 = _ema(bC, 50)
    b_tr = _tr([b["high"] for b in btc], [b["low"] for b in btc], bC)
    b_atr = _wilder(b_tr, 14)
    eT = [b["time"] for b in eth]
    eC = [b["close"] for b in eth]
    fT = [t for t, _ in funding]
    fR = [r for _, r in funding]
    def ret(arr, j, k):
        return (arr[j] / arr[j - k] - 1) * 100 if j - k >= 0 and arr[j - k] > 0 else 0.0
    rows = []
    for i in range(start, n):
        a = atr[i]
        c = C[i]
        if a is None or a <= 0 or c <= 0 or em[200][i] is None:
            rows.append(None)
            continue
        f = []
        # trend / EMAs
        for k in (9, 20, 50, 100, 200):
            f.append(_cl((c - em[k][i]) / a))
        for k in (20, 50, 200):
            f.append(_cl((em[k][i] - em[k][i - 5]) / a) if em[k][i - 5] is not None else 0.0)
        f.append(float((em[20][i] > em[50][i]) + (em[50][i] > em[100][i]) + (em[100][i] > em[200][i])))
        f.append(_cl(macd[i] / a))
        f.append(_cl((macd[i] - msig[i]) / a))
        f.append(_cl(((macd[i] - msig[i]) - (macd[i - 3] - msig[i - 3])) / a))
        f.append(float(st_dir[i]))
        f.append(_cl((c - st_line[i]) / a) if st_line[i] is not None else 0.0)
        top, bot = max(sb[i - 26] if i >= 26 else sb[i], (tenkan[i - 26] + kijun[i - 26]) / 2 if i >= 26 else kijun[i]), \
            min(sb[i - 26] if i >= 26 else sb[i], (tenkan[i - 26] + kijun[i - 26]) / 2 if i >= 26 else kijun[i])
        f.append(_cl((c - top) / a) if c > top else (_cl((c - bot) / a) if c < bot else 0.0))
        f.append(_cl((tenkan[i] - kijun[i]) / a))
        vw = s_pv[i] / s_v[i] if s_v[i] else c
        f.append(_cl((c - vw) / a))
        f.append(adx[i] or 0.0)
        f.append((pdi[i] or 0.0) - (ndi[i] or 0.0))
        # oscillators
        f.append(rsi14[i] or 50.0)
        f.append(rsi7[i] or 50.0)
        f.append((rsi14[i] or 50.0) - (rsi14[i - 3] or 50.0))
        rng = hh14[i] - ll14[i]
        sk = (c - ll14[i]) / rng * 100 if rng > 0 else 50.0
        f.append(sk)
        f.append(-100 + sk)   # williams %R
        f.append(_cl((tp[i] - tp_sma[i]) / (0.015 * md[i]), -500, 500) if md[i] else 0.0)
        for k in (1, 3, 6, 12, 24, 72, 168):
            f.append(_cl(ret(C, i, k), -80, 300))
        # divergence: a new 14-bar extreme without the RSI's
        div = 0.0
        if i >= 15 and rsi14[i - 14] is not None:
            if H[i] >= hh14[i] and rsi14[i] < max(r for r in rsi14[i - 14:i] if r is not None):
                div = -1.0
            elif L[i] <= ll14[i] and rsi14[i] > min(r for r in rsi14[i - 14:i] if r is not None):
                div = 1.0
        f.append(div)
        # volatility
        f.append(a / c * 100)
        f.append(a / atr100[i] if atr100[i] else 1.0)
        bw = 4 * sd20[i] / sma20[i] * 100 if sma20[i] else 0.0
        f.append(bw)
        f.append((c - (sma20[i] - 2 * sd20[i])) / (4 * sd20[i]) if sd20[i] else 0.5)
        rr14 = hh14[i] - ll14[i]
        f.append(100 * math.log10(sum(tr[i - 13:i + 1]) / rr14) / math.log10(14) if rr14 > 0 else 50.0)
        f.append((hh24[i] - ll24[i]) / a)
        f.append((hh168[i] - ll168[i]) / a)
        f.append(rv24[i] / rv168[i] if rv168[i] else 1.0)
        # candles
        rgn = H[i] - L[i]
        f.append((c - O[i]) / rgn if rgn > 0 else 0.0)
        f.append((H[i] - max(O[i], c)) / rgn if rgn > 0 else 0.0)
        f.append((min(O[i], c) - L[i]) / rgn if rgn > 0 else 0.0)
        f.append(_cl((c - O[i - 2]) / a))
        f.append(_cl((O[i] - C[i - 1]) / a))
        stk = 0
        for k in range(i, max(i - 20, 0), -1):
            if C[k] > C[k - 1]:
                if stk < 0:
                    break
                stk += 1
            elif C[k] < C[k - 1]:
                if stk > 0:
                    break
                stk -= 1
            else:
                break
        f.append(float(stk))
        f.append(1.0 if H[i] <= H[i - 1] and L[i] >= L[i - 1] else 0.0)
        f.append(1.0 if c > O[i] and O[i] <= C[i - 1] and c >= O[i - 1] and C[i - 1] < O[i - 1] else
                 (-1.0 if c < O[i] and O[i] >= C[i - 1] and c <= O[i - 1] and C[i - 1] > O[i - 1] else 0.0))
        # volume
        f.append(_cl((lv[i] - lv_m[i]) / lv_s[i], -10, 10) if lv_s[i] else 0.0)
        f.append(_cl(math.log((sum(V[i - 23:i + 1]) + 1e-9) / (sum(V[i - 167:i + 1]) / 7 + 1e-9)), -10, 10) if i >= 167 else 0.0)
        vm = s_v[i] or 1e-9
        f.append(_cl((obv[i] - obv[i - 24]) / (vm * 24), -5, 5) if i >= 24 else 0.0)
        up = sum(V[k] for k in range(i - 23, i + 1) if C[k] > O[k])
        f.append(up / (sum(V[i - 23:i + 1]) + 1e-9))
        # position
        for hh, ll in ((hh24, ll24), (hh168, ll168), (hh720, ll720)):
            r_ = hh[i] - ll[i]
            f.append((c - ll[i]) / r_ if r_ > 0 else 0.5)
        f.append(_cl((hh720[i] - c) / a, 0, 500))
        f.append(_cl((c - ll720[i]) / a, 0, 500))
        mag = 10 ** math.floor(math.log10(c))
        f.append(min(abs(c / mag - round(c / mag)), abs(c / mag * 2 - round(c / mag * 2)) / 2) * mag / a)
        # 4h
        k4 = i4[i]
        if k4 >= 0 and I4["atr"][k4]:
            a4 = I4["atr"][k4]
            f += [I4["rsi"][k4] or 50.0, _cl((c - (I4["e20"][k4] or c)) / a4), _cl((c - (I4["e50"][k4] or c)) / a4),
                  _cl(((I4["macd"][k4] or 0) - (I4["sig"][k4] or 0)) / a4),
                  ((c - I4["ll14"][k4]) / (I4["hh14"][k4] - I4["ll14"][k4]) * 100 if I4["hh14"][k4] > I4["ll14"][k4] else 50.0)]
        else:
            f += [50.0, 0.0, 0.0, 0.0, 50.0]
        # daily
        kd = idd[i]
        if kd >= 0 and ID["atr"][kd]:
            ad = ID["atr"][kd]
            f += [ID["rsi"][kd] or 50.0, _cl((c - (ID["e20"][kd] or c)) / ad), _cl((c - (ID["e50"][kd] or c)) / ad),
                  _cl((c - (ID["e200"][kd] or c)) / ad), ad / c * 100,
                  ((c - ID["ll30"][kd]) / (ID["hh30"][kd] - ID["ll30"][kd]) if ID["hh30"][kd] > ID["ll30"][kd] else 0.5),
                  ((c - ID["ll365"][kd]) / (ID["hh365"][kd] - ID["ll365"][kd]) if ID["hh365"][kd] > ID["ll365"][kd] else 0.5)]
            ds = 0
            dC = ID["C"]
            for k in range(kd, max(kd - 10, 0), -1):
                if dC[k] > dC[k - 1]:
                    if ds < 0:
                        break
                    ds += 1
                elif dC[k] < dC[k - 1]:
                    if ds > 0:
                        break
                    ds -= 1
                else:
                    break
            f.append(float(ds))
        else:
            f += [50.0, 0.0, 0.0, 0.0, 0.0, 0.5, 0.5, 0.0]
        kw = iw[i]
        f.append(_cl((c / we21[kw] - 1) * 100, -90, 500) if kw >= 0 and we21[kw] else 0.0)
        # time
        tt = T[i] + 3600
        hr = (tt // 3600) % 24
        dw = (tt // 86400 + 3) % 7
        f += [float(hr), float(dw), float(dw >= 5)]
        # BTC / ETH
        bj = bisect.bisect_right(bT, T[i]) - 1
        if bj >= 168:
            f += [ret(bC, bj, 1), ret(bC, bj, 4), ret(bC, bj, 24), ret(bC, bj, 168), b_rsi[bj] or 50.0,
                  _cl((bC[bj] - (b_e50[bj] or bC[bj])) / (b_atr[bj] or 1)), (b_atr[bj] or 0) / bC[bj] * 100]
            f.append(_cl(ret(C, i, 24) - ret(bC, bj, 24), -80, 300))
            f.append(_cl(ret(C, i, 168) - ret(bC, bj, 168), -80, 300))
        else:
            f += [0.0, 0.0, 0.0, 0.0, 50.0, 0.0, 0.0, 0.0, 0.0]
        ej = bisect.bisect_right(eT, T[i]) - 1
        f.append(ret(eC, ej, 24) if ej >= 24 else 0.0)
        # funding (known: the rates settled up to the bar's close)
        fj = bisect.bisect_right(fT, T[i] + 3600) - 1
        if fj >= 0:
            f.append(fR[fj] * 100)
            f.append(sum(fR[max(0, fj - 2):fj + 1]) / len(fR[max(0, fj - 2):fj + 1]) * 100)
            w = fR[max(0, fj - 89):fj + 1]
            mu = sum(w) / len(w)
            sd = math.sqrt(sum((x - mu) ** 2 for x in w) / len(w)) if len(w) > 2 else 0.0
            f.append(_cl((fR[fj] - mu) / sd, -10, 10) if sd > 0 else 0.0)
        else:
            f += [0.0, 0.0, 0.0]
        rows.append([round(float(x), 5) for x in f])
    return rows

NAMES = (["d_e9", "d_e20", "d_e50", "d_e100", "d_e200", "sl_e20", "sl_e50", "sl_e200", "e_stack", "macd", "macd_h", "macd_h_ch",
          "st_dir", "st_dist", "ichi", "tk_kj", "vwap", "adx", "di",
          "rsi14", "rsi7", "rsi_ch", "stoch", "will", "cci"] + [f"roc{k}" for k in (1, 3, 6, 12, 24, 72, 168)] +
         ["div", "atr_pct", "atr_ratio", "bb_w", "bb_b", "chop", "rng24", "rng168", "rv_ratio",
          "body", "uwick", "lwick", "mv3", "gap", "streak", "inside", "engulf",
          "vol_z", "vol24", "obv24", "upvol",
          "pos24", "pos168", "pos720", "from_hi", "from_lo", "round",
          "h4_rsi", "h4_e20", "h4_e50", "h4_macd", "h4_stoch",
          "d_rsi", "dd_e20", "dd_e50", "dd_e200", "d_atr", "d_pos30", "d_pos365", "d_streak", "w_e21",
          "hour", "dow", "weekend",
          "b_r1", "b_r4", "b_r24", "b_r168", "b_rsi", "b_e50", "b_atr", "rs24", "rs168", "e_r24",
          "fund", "fund3", "fund_z"])
