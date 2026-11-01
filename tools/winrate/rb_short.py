"""📈 breakout redone short (the user: the daily / 12h breakout holds up to half a year — "перейди на мельче таймфрейм и
переделай индикатор"): a close out of a narrow range (N bars < K x ATR100) in the direction of the chart's own EMA200, the
entry at the next bar's open, on 1h / 2h / 4h, the hold capped at 2 / 5 / 10 days; stops 1 / 1.5 / 2 ATR; exits: a take
2 / 3R, the close beyond the 10 / 20-bar low / high, a quarter at +1R then break-even and the rest by the take 3R / the
10-bar channel. The research's 127 coins, Binance 1h 2021-2026. -> <LABSTORE>/wf/rbs_<tf>.npz (one row an event)
usage: rb_short.py TFH [coins...]"""
import sys, os, re, gzip, numpy as np
from multiprocessing import Pool
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
TFH = int(sys.argv[1]) if len(sys.argv) > 1 else 4
NS, KMAX = ((20, 30, 50) if TFH < 24 else (15, 20, 30)), 4.0
STOPS = (1.0, 1.5, 2.0)
EXITS = ("t2", "t3", "dc10", "dc20", "p1t3", "p1dc10") + (("t5", "p1t5") if TFH >= 12 else ())
HOLDS_D = (1, 2, 5) if TFH < 12 else (5, 10, 20)   # 12h / 1d: the deployed signal, the hold capped
FEE, FUND = 0.001, 0.0003


def coins():
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "vp_poc_screener.py")).read()
    m = re.search(r'RESEARCH_COINS_127 = tuple\("""(.*?)"""', src, re.S)
    out = []
    for g in m.group(1).split():
        b = g.replace("_USDT", "")
        for c in (b + "USDT", "1000" + b + "USDT"):
            if os.path.exists(f"{ST}/data/1h/{c}.csv.gz"):
                out.append(c); break
    return sorted(set(out))


def load(sym):
    a = np.loadtxt(gzip.open(f"{ST}/data/1h/{sym}.csv.gz", "rt"), delimiter=",", usecols=(0, 1, 2, 3, 4))
    if TFH == 1:
        return a[:, 0], a[:, 1], a[:, 2], a[:, 3], a[:, 4]
    g = (a[:, 0] // (TFH * 3600)).astype(np.int64)
    cut = np.flatnonzero(np.diff(g)) + 1
    st = np.r_[0, cut]; en = np.r_[cut, len(a)]
    full = (en - st) == TFH   # whole bars only
    st, en = st[full], en[full]
    T = g[st] * TFH * 3600
    O = a[st, 1]; C = a[en - 1, 4]
    H = np.maximum.reduceat(a[:, 2], np.r_[0, cut])[full]; L = np.minimum.reduceat(a[:, 3], np.r_[0, cut])[full]
    return T.astype(float), O, H, L, C


def rmax(x, n):
    from numpy.lib.stride_tricks import sliding_window_view as sw
    o = np.full(len(x), np.nan); o[n - 1:] = sw(x, n).max(1); return o


def rmin(x, n):
    from numpy.lib.stride_tricks import sliding_window_view as sw
    o = np.full(len(x), np.nan); o[n - 1:] = sw(x, n).min(1); return o


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


def first(c):
    return int(np.argmax(c)) if c.any() else len(c)


def outcome(O, H, L, C, i, s, a, DCL, DCH, hb):
    """R and bars for each stop x exit at the hold hb bars (NaN when the data ends first)"""
    y = np.full((len(STOPS), len(EXITS), 2), np.nan, np.float32)
    n = len(C)
    if i + 1 + hb > n:
        return y
    e = O[i + 1]; sg = slice(i + 1, i + 1 + hb)
    Hs, Ls, Cs = H[sg], L[sg], C[sg]
    fav = Hs if s > 0 else Ls; adv = Ls if s > 0 else Hs
    for si, ks in enumerate(STOPS):
        risk = ks * a
        if risk <= e * 0.003:
            continue
        fee = lambda j: (e * FEE + e * FUND * (j + 1) * TFH / 24) / risk
        R = lambda px: s * (px - e) / risk
        js = first((adv <= e - risk) if s > 0 else (adv >= e + risk))
        for xi, xn in enumerate(EXITS):
            if xn[0] == "t":
                tp = e + s * float(xn[1:]) * risk
                jt = first((fav >= tp) if s > 0 else (fav <= tp))
                if js <= jt and js < hb: r, j = -1.0, js
                elif jt < hb: r, j = float(xn[1:]), jt
                else: r, j = R(Cs[-1]), hb - 1
            elif xn.startswith("dc"):
                N = int(xn[2:]); lv = (DCL[N] if s > 0 else DCH[N])[sg]
                jd = first((Cs < lv) if s > 0 else (Cs > lv))
                if js <= jd and js < hb: r, j = -1.0, js
                elif jd < hb: r, j = R(Cs[jd]), jd
                else: r, j = R(Cs[-1]), hb - 1
            else:   # p1..: a quarter off at +1R, the stop to the entry, the rest by the take 3R (5R) / the 10-bar channel
                jb = first((fav >= e + risk) if s > 0 else (fav <= e - risk))
                if xn in ("p1t3", "p1t5"):
                    tp = e + s * float(xn[3:]) * risk; xc = (fav >= tp) if s > 0 else (fav <= tp); xpx = np.full(hb, tp)
                else:
                    lv = (DCL[10] if s > 0 else DCH[10])[sg]; xc = (Cs < lv) if s > 0 else (Cs > lv); xpx = Cs
                jx = first(xc)
                if js < hb and js <= min(jb, jx): r, j = -1.0, js
                elif jx < jb and jx < hb: r, j = R(xpx[jx]), jx
                elif jb >= hb: r, j = R(Cs[-1]), hb - 1
                else:
                    k = jb + 1
                    jbe = k + first((adv[k:] <= e) if s > 0 else (adv[k:] >= e)); jx2 = k + first(xc[k:])
                    if jbe < hb and jbe <= jx2: rest, j = 0.0, jbe
                    elif jx2 < hb: rest, j = R(xpx[jx2]), jx2
                    else: rest, j = R(Cs[-1]), hb - 1
                    r = 0.25 + 0.75 * rest
            y[si, xi] = (r - fee(j), j + 1)
    return y


def run(sym):
    T, O, H, L, C = load(sym)
    if len(C) < 400:
        return None
    tr = np.maximum(H[1:], C[:-1]) - np.minimum(L[1:], C[:-1]); tr = np.r_[H[0] - L[0], tr]
    atr = wilder(tr, 14); a100 = np.convolve(tr, np.ones(100) / 100, "full")[:len(tr)]; a100[:99] = np.nan
    e200 = ema(C, 200)
    DCL = {N: np.r_[np.nan, rmin(L, N)[:-1]] for N in (10, 20)}   # the N bars before the bar
    DCH = {N: np.r_[np.nan, rmax(H, N)[:-1]] for N in (10, 20)}
    hbs = [int(d * 24 / TFH) for d in HOLDS_D]
    rows = []
    for N in NS:
        hh = np.r_[np.nan, rmax(H, N)[:-1]]; ll = np.r_[np.nan, rmin(L, N)[:-1]]   # the range of the N bars before
        up = (C > hh) & (np.r_[False, C[:-1] <= hh[:-1]]); dn = (C < ll) & (np.r_[False, C[:-1] >= ll[:-1]])
        rg = (hh - ll) / a100
        for i in np.flatnonzero((up | dn) & (rg < KMAX) & ~np.isnan(atr) & (np.arange(len(C)) >= 210)):
            s = 1 if up[i] else -1
            if s * (C[i] - e200[i]) <= 0:
                continue
            y = np.stack([outcome(O, H, L, C, i, s, atr[i], DCL, DCH, hb) for hb in hbs], 2)   # stop x exit x hold x (r, bars)
            if np.isnan(y[..., 0]).all():
                continue
            rows.append((T[i] + TFH * 3600, s, N, rg[i], s * (C[i] - (hh[i] if s > 0 else ll[i])) / atr[i], O[i + 1], atr[i], y))
    return sym, rows


if __name__ == "__main__":
    cs = sys.argv[2:] or coins()
    out = {k: [] for k in ("t", "side", "N", "rg", "brk", "e", "atr", "y", "sym")}
    with Pool(4) as P:
        for res in P.imap_unordered(run, cs):
            if not res: continue
            sym, rows = res
            for r in rows:
                for k, v in zip(("t", "side", "N", "rg", "brk", "e", "atr", "y"), r): out[k].append(v)
                out["sym"].append(sym)
            print(sym, len(rows), flush=True)
    os.makedirs(f"{ST}/wf", exist_ok=True)
    np.savez_compressed(f"{ST}/wf/rbs_{TFH}.npz", **{k: np.array(v) for k, v in out.items()})
    print(f"rbs {TFH}h done: {len(out['t'])} events", flush=True)
