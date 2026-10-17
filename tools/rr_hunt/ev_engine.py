"""High-RR hunt: the project's archived indicators (+ new ones) as event generators on 1h / 4h / 1d of every coin,
each event with fixed far takes AND trailing exits; features = event's own + the 89 Neuro features of the 1h bar
closing with it. Saved per coin: X, Y [events, stops, exits], meta (t, family, tf, side)."""
import sys, os, time
ARGS = sys.argv[1:]
import numpy as np
from common import V, load, D
import nx_feat
from nx_build import funding
import multiprocessing as mp
FAMS = ["donch20", "donch55", "squeeze", "sweep", "retest", "pullback", "rangebrk", "amd", "mrext", "bigcandle"]
TFS = {"1h": 1, "4h": 4, "1d": 24}
HOLD = {1: 240, 4: 270, 24: 180}
STOPS = (1.0, 1.5, 3.0)
EXITS = ("t3", "t5", "t8", "t12", "t20", "ch3", "ch5", "ch8", "dc10", "dc20", "dc50")
FEE, FUND = 0.001, 0.0003
EV_NAMES = ["fam", "tf", "side", "atrp", "ext_atr", "body", "rng_atr", "trend50", "trend200", "rsi"]
_REF = {}
def ref():
    if not _REF:
        _REF["btc"], _REF["eth"] = load("BTCUSDT"), load("ETHUSDT")
    return _REF

def ema(x, n):
    out = np.empty_like(x); k = 2 / (n + 1); e = x[0]
    for i, v in enumerate(x):
        e = v if i == 0 else e + k * (v - e); out[i] = e
    return out
def sma(x, n):
    c = np.cumsum(np.insert(x, 0, 0.0)); out = np.full(len(x), np.nan); out[n - 1:] = (c[n:] - c[:-n]) / n; return out
def rstd(x, n):
    m = sma(x, n); m2 = sma(x * x, n); return np.sqrt(np.maximum(0, m2 - m * m))
def rmax(x, n):   # max over the n bars BEFORE i (i excluded)
    out = np.full(len(x), np.nan)
    from collections import deque
    dq = deque()
    for i in range(len(x)):
        if i >= 1:
            j = i - 1
            while dq and x[dq[-1]] <= x[j]:
                dq.pop()
            dq.append(j)
            while dq[0] < i - n:
                dq.popleft()
            if i >= n:
                out[i] = x[dq[0]]
    return out
def rmin(x, n):
    return -rmax(-x, n)
def rsi(c, n=14):
    return np.array([v if v is not None else 50.0 for v in nx_feat._rsi(list(c), n)])
def pivots(H, L, k=5):
    """confirmed swing highs / lows: (confirm index, price)"""
    ph, pl = [], []
    for j in range(k, len(H) - k):
        if H[j] == max(H[j - k:j + k + 1]):
            ph.append((j + k, H[j]))
        if L[j] == min(L[j - k:j + k + 1]):
            pl.append((j + k, L[j]))
    return ph, pl

def events(O, H, L, C):
    """{family: [(i, side)]} on one chart, all causal (bar i closed)"""
    n = len(C)
    tr = np.array(nx_feat._tr(list(H), list(L), list(C)))
    atr = np.array([v if v is not None else np.nan for v in nx_feat._wilder(list(tr), 14)])
    e20, e50, e200 = ema(C, 20), ema(C, 50), ema(C, 200)
    m20, sd20 = sma(C, 20), rstd(C, 20)
    r14 = rsi(C)
    ev = {f: [] for f in FAMS}
    for N, f in ((20, "donch20"), (55, "donch55")):
        hh, ll = rmax(H, N), rmin(L, N)
        up = C > hh; dn = C < ll
        for i in range(N + 1, n):
            if up[i] and not up[i - 1]:
                ev[f].append((i, 1))
            elif dn[i] and not dn[i - 1]:
                ev[f].append((i, -1))
    sq = (m20 + 2 * sd20 < e20 + 1.5 * atr) & (m20 - 2 * sd20 > e20 - 1.5 * atr)
    run = 0
    for i in range(1, n):
        if sq[i - 1]:
            run += 1
        else:
            run = 0
        if run >= 6 and not sq[i]:
            ev["squeeze"].append((i, 1 if C[i] > m20[i] else -1))
    ph, pl = pivots(H, L)
    a, b = 0, 0
    last_h = last_l = None
    used_h = used_l = False
    broken_h = broken_l = None   # (level, bar broken)
    for i in range(n):
        while a < len(ph) and ph[a][0] <= i:
            last_h, used_h = ph[a][1], False; a += 1
        while b < len(pl) and pl[b][0] <= i:
            last_l, used_l = pl[b][1], False; b += 1
        if i < 210 or np.isnan(atr[i]):
            continue
        if last_h is not None and not used_h:
            if H[i] > last_h and C[i] < last_h:
                ev["sweep"].append((i, -1)); used_h = True
            elif C[i] > last_h:
                broken_h, used_h = (last_h, i), True
        if last_l is not None and not used_l:
            if L[i] < last_l and C[i] > last_l:
                ev["sweep"].append((i, 1)); used_l = True
            elif C[i] < last_l:
                broken_l, used_l = (last_l, i), True
        if broken_h and i > broken_h[1] + 1:
            lv = broken_h[0]
            if i > broken_h[1] + 30 or C[i] < lv - atr[i]:
                broken_h = None
            elif L[i] <= lv + 0.2 * atr[i] and C[i] > lv:
                ev["retest"].append((i, 1)); broken_h = None
        if broken_l and i > broken_l[1] + 1:
            lv = broken_l[0]
            if i > broken_l[1] + 30 or C[i] > lv + atr[i]:
                broken_l = None
            elif H[i] >= lv - 0.2 * atr[i] and C[i] < lv:
                ev["retest"].append((i, -1)); broken_l = None
    last_touch = -99
    for i in range(210, n):
        upt = e20[i] > e50[i] > e200[i] and C[i] > e200[i]
        dnt = e20[i] < e50[i] < e200[i] and C[i] < e200[i]
        if upt and L[i] <= e20[i] < C[i]:
            if i - last_touch > 5:
                ev["pullback"].append((i, 1))
            last_touch = i
        elif dnt and H[i] >= e20[i] > C[i]:
            if i - last_touch > 5:
                ev["pullback"].append((i, -1))
            last_touch = i
    atr100 = sma(tr, 100)
    hh20, ll20 = rmax(H, 20), rmin(L, 20)
    for i in range(120, n):
        if hh20[i] - ll20[i] < 3 * atr100[i]:
            if C[i] > hh20[i] and C[i - 1] <= hh20[i - 1]:
                ev["rangebrk"].append((i, 1))
            elif C[i] < ll20[i] and C[i - 1] >= ll20[i - 1]:
                ev["rangebrk"].append((i, -1))
    for i in range(30, n):
        rh, rl = H[i - 13:i - 1].max(), L[i - 13:i - 1].min()
        if np.isnan(atr[i]) or rh - rl > 2 * atr[i]:
            continue
        if L[i - 1] < rl and C[i] > rl and C[i] > O[i]:
            ev["amd"].append((i, 1))
        elif H[i - 1] > rh and C[i] < rh and C[i] < O[i]:
            ev["amd"].append((i, -1))
    last = -99
    for i in range(30, n):
        if i - last < 5:
            continue
        if r14[i] < 20 and C[i] < m20[i] - 2.5 * sd20[i]:
            ev["mrext"].append((i, 1)); last = i
        elif r14[i] > 80 and C[i] > m20[i] + 2.5 * sd20[i]:
            ev["mrext"].append((i, -1)); last = i
    for i in range(30, n):
        rg = H[i] - L[i]
        if not np.isnan(atr[i - 1]) and rg > 3 * atr[i - 1] and abs(C[i] - O[i]) > 0.7 * rg:
            ev["bigcandle"].append((i, 1 if C[i] > O[i] else -1))
    ind = {"atr": atr, "e50": e50, "e200": e200, "rsi": r14}
    return ev, ind

def outcomes(O, H, L, C, i, s, a, hrs, DC):
    """[stops, exits] R of an entry at bar i+1's open"""
    n = len(C)
    Hm = HOLD[hrs]
    y = np.full((len(STOPS), len(EXITS), 2), np.nan, dtype=np.float32)   # (R, bars held)
    if i + 1 + Hm > n or not a or a != a:
        return y
    e = O[i + 1]
    seg = slice(i + 1, i + 1 + Hm)
    Os, Hs, Ls, Cs = O[seg], H[seg], L[seg], C[seg]
    for si, ks in enumerate(STOPS):
        risk = ks * a
        if risk <= e * 0.002:
            continue
        stop = e - s * risk
        hit_s = (Ls <= stop) if s > 0 else (Hs >= stop)
        js = int(np.argmax(hit_s)) if hit_s.any() else Hm
        def fin(j, ex):
            return ((s * (ex - e) - e * FEE - e * FUND * (j + 1) * hrs / 24) / risk, j + 1)
        for xi, ex_name in enumerate(EXITS):
            if ex_name[0] == "t":
                R = float(ex_name[1:])
                tp = e + s * R * risk
                ht = (Hs >= tp) if s > 0 else (Ls <= tp)
                jt = int(np.argmax(ht)) if ht.any() else Hm
                if js <= jt and js < Hm:
                    y[si, xi, :] = fin(js, stop)
                elif jt < Hm:
                    y[si, xi, :] = fin(jt, tp)
                else:
                    y[si, xi, :] = fin(Hm - 1, Cs[-1])
            elif ex_name.startswith("ch"):
                k = float(ex_name[2:])
                if s > 0:
                    lvl = np.maximum(stop, np.concatenate([[stop], np.maximum.accumulate(Cs)[:-1] - k * a]))
                    hit = Ls <= lvl
                else:
                    lvl = np.minimum(stop, np.concatenate([[stop], np.minimum.accumulate(Cs)[:-1] + k * a]))
                    hit = Hs >= lvl
                if hit.any():
                    j = int(np.argmax(hit))
                    px = min(Os[j], lvl[j]) if s > 0 else max(Os[j], lvl[j])
                    if j == 0:
                        px = lvl[j]
                    y[si, xi, :] = fin(j, px)
                else:
                    y[si, xi, :] = fin(Hm - 1, Cs[-1])
            else:   # dcN: out at the close beyond the N-bar low (long) / high (short)
                N = int(ex_name[2:])
                lv = DC[N][0][seg] if s > 0 else DC[N][1][seg]
                cond = (Cs < lv) if s > 0 else (Cs > lv)
                jd = int(np.argmax(cond)) if cond.any() else Hm
                if js <= jd and js < Hm:
                    y[si, xi, :] = fin(js, stop)
                elif jd < Hm:
                    y[si, xi, :] = fin(jd, Cs[jd])
                else:
                    y[si, xi, :] = fin(Hm - 1, Cs[-1])
    return y

def run(sym):
    fn = f"{D}/ev/{sym}.npz"
    if os.path.exists(fn):
        return sym, -1
    t0 = time.time()
    h1 = load(sym)
    if not h1 or len(h1) < 24 * 120:
        return sym, 0
    R_ = ref()
    h4, d1 = V._oc_agg(h1, 4), V._oc_agg(h1, 24)
    rows = nx_feat.nx_series(h1, h4, d1, V.emw_bars(d1, "1w"), R_["btc"], R_["eth"], funding(sym))
    h1_end = np.array([c["time"] + 3600 for c in h1])
    Xs, Ys, M = [], [], []
    for tf, hrs in TFS.items():
        cs = h1 if hrs == 1 else (h4 if hrs == 4 else d1)
        O = np.array([c["open"] for c in cs]); H = np.array([c["high"] for c in cs]); L = np.array([c["low"] for c in cs]); C = np.array([c["close"] for c in cs])
        T = np.array([c["time"] for c in cs])
        ev, ind = events(O, H, L, C)
        DC = {N: (rmin(L, N), rmax(H, N)) for N in (10, 20, 50)}
        for fi, f in enumerate(FAMS):
            for i, s in ev[f]:
                if i < 210 or i >= len(C) - 1:
                    continue
                a = ind["atr"][i]
                if not a or a != a:
                    continue
                k1 = np.searchsorted(h1_end, T[i] + hrs * 3600, side="right") - 1
                if k1 < 0 or rows[k1] is None:
                    continue
                rg = H[i] - L[i]
                f_ev = [float(fi), float(hrs), float(s), a / C[i] * 100, s * (C[i] - (ind["e50"][i])) / a,
                        s * (C[i] - O[i]) / rg if rg > 0 else 0.0, rg / a, s * (C[i] - ind["e50"][i]) / C[i] * 100,
                        s * (C[i] - ind["e200"][i]) / C[i] * 100, ind["rsi"][i]]
                Xs.append(f_ev + rows[k1])
                Ys.append(outcomes(O, H, L, C, i, s, a, hrs, DC))
                M.append((int(T[i] + hrs * 3600), fi, hrs, s))
    os.makedirs(f"{D}/ev", exist_ok=True)
    M = np.array(M, dtype=np.int64).reshape(-1, 4)
    np.savez_compressed(fn, X=np.array(Xs, dtype=np.float32), Y=np.array(Ys, dtype=np.float32), t=M[:, 0], fam=M[:, 1], tf=M[:, 2], side=M[:, 3])
    return sym, len(Xs), round(time.time() - t0)

if __name__ == "__main__":
    syms = ARGS or sorted(f[:-4] for f in os.listdir(f"{D}/data/1h"))
    with mp.Pool(int(os.environ.get("NP", 4))) as p:
        for res in p.imap_unordered(run, syms):
            print(*res, flush=True)
