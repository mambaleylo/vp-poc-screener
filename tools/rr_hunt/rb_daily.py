"""Range breakout on the daily chart, deep sweep: range length N, compression k (range < k x ATR100), the coin's
own-trend gate, stops, takes / trailing exits. Per coin: events + outcomes; pooled replay later (rb_tab.py)."""
import sys, os, time, pickle
ARGS = sys.argv[1:]
import numpy as np
from common import V, load, D
import nx_feat
import multiprocessing as mp
from ev_engine import ema, sma, rmax, rmin
NS = (10, 15, 20, 30, 40)
KS = (2.0, 2.5, 3.0, 4.0, 6.0)
STOPS = (1.0, 1.5, 2.0, 3.0)
EXITS = ("t3", "t5", "t8", "t12", "t20", "ch3", "ch5", "ch8", "dc10", "dc20", "dc50")
HOLD = 180
FEE, FUND = 0.001, 0.0003

def outcomes(O, H, L, C, i, s, a, DC):
    n = len(C)
    y = np.full((len(STOPS), len(EXITS), 2), np.nan, dtype=np.float32)
    e = O[i + 1]
    Hm = min(HOLD, n - i - 1)
    if Hm < 30:
        return y
    seg = slice(i + 1, i + 1 + Hm)
    Os, Hs, Ls, Cs = O[seg], H[seg], L[seg], C[seg]
    for si, ks in enumerate(STOPS):
        risk = ks * a
        if risk <= e * 0.003:
            continue
        stop = e - s * risk
        hit_s = (Ls <= stop) if s > 0 else (Hs >= stop)
        js = int(np.argmax(hit_s)) if hit_s.any() else Hm
        def fin(j, ex):
            return ((s * (ex - e) - e * FEE - e * FUND * (j + 1)) / risk, j + 1)
        for xi, xn in enumerate(EXITS):
            if xn[0] == "t":
                tp = e + s * float(xn[1:]) * risk
                ht = (Hs >= tp) if s > 0 else (Ls <= tp)
                jt = int(np.argmax(ht)) if ht.any() else Hm
                if js <= jt and js < Hm:
                    y[si, xi] = fin(js, stop)
                elif jt < Hm:
                    y[si, xi] = fin(jt, tp)
                else:
                    y[si, xi] = fin(Hm - 1, Cs[-1]) if Hm == HOLD else (np.nan, np.nan)
            elif xn.startswith("ch"):
                k = float(xn[2:])
                if s > 0:
                    lvl = np.maximum(stop, np.concatenate([[stop], np.maximum.accumulate(Cs)[:-1] - k * a])); hit = Ls <= lvl
                else:
                    lvl = np.minimum(stop, np.concatenate([[stop], np.minimum.accumulate(Cs)[:-1] + k * a])); hit = Hs >= lvl
                if hit.any():
                    j = int(np.argmax(hit))
                    px = lvl[j] if j == 0 else (min(Os[j], lvl[j]) if s > 0 else max(Os[j], lvl[j]))
                    y[si, xi] = fin(j, px)
                else:
                    y[si, xi] = fin(Hm - 1, Cs[-1]) if Hm == HOLD else (np.nan, np.nan)
            else:
                N = int(xn[2:])
                lv = DC[N][0][seg] if s > 0 else DC[N][1][seg]
                cond = (Cs < lv) if s > 0 else (Cs > lv)
                jd = int(np.argmax(cond)) if cond.any() else Hm
                if js <= jd and js < Hm:
                    y[si, xi] = fin(js, stop)
                elif jd < Hm:
                    y[si, xi] = fin(jd, Cs[jd])
                else:
                    y[si, xi] = fin(Hm - 1, Cs[-1]) if Hm == HOLD else (np.nan, np.nan)
    return y

def run(sym):
    fn = f"{D}/rb/{sym}.pkl"
    if os.path.exists(fn):
        return sym, -1
    h1 = load(sym)
    if not h1 or len(h1) < 24 * 300:
        return sym, 0
    d1 = V._oc_agg(h1, 24)
    O = np.array([c["open"] for c in d1]); H = np.array([c["high"] for c in d1]); L = np.array([c["low"] for c in d1]); C = np.array([c["close"] for c in d1])
    T = np.array([c["time"] + 86400 for c in d1])
    tr = np.array(nx_feat._tr(list(H), list(L), list(C)))
    atr = np.array([v if v is not None else np.nan for v in nx_feat._wilder(list(tr), 14)])
    atr100 = sma(tr, 100)
    e200 = ema(C, 200)
    w1 = V.emw_bars(d1, "1w")
    wC = np.array([b["close"] for b in w1]); wT = np.array([V.emw_next_period(b["time"], "1w") for b in w1]); we21 = ema(wC, 21) if len(wC) else wC
    DC = {N: (rmin(L, N), rmax(H, N)) for N in (10, 20, 50)}
    out = []
    for N in NS:
        hh, ll = rmax(H, N), rmin(L, N)
        for i in range(max(N, 120), len(C) - 1):
            if np.isnan(atr[i]) or np.isnan(atr100[i]):
                continue
            rg = (hh[i] - ll[i]) / atr100[i]
            s = 1 if (C[i] > hh[i] and C[i - 1] <= hh[i - 1]) else (-1 if (C[i] < ll[i] and C[i - 1] >= ll[i - 1]) else 0)
            if not s or rg >= max(KS):
                continue
            kw = np.searchsorted(wT, T[i], side="right") - 1
            f = {"N": N, "rg": rg, "own200": s * (C[i] - e200[i]) > 0 if i >= 200 else None,
                 "week": (s * (wC[kw] - we21[kw]) > 0) if kw >= 21 else None, "dist200": s * (C[i] / e200[i] - 1) * 100,
                 "brk": s * (C[i] - (hh[i] if s > 0 else ll[i])) / atr[i], "atrp": atr[i] / C[i] * 100}
            out.append((int(T[i]), s, f, outcomes(O, H, L, C, i, s, atr[i], DC)))
    os.makedirs(f"{D}/rb", exist_ok=True)
    pickle.dump(out, open(fn, "wb"))
    return sym, len(out)

if __name__ == "__main__":
    syms = ARGS or sorted(f[:-4] for f in os.listdir(f"{D}/data/1h"))
    with mp.Pool(int(os.environ.get("NP", 4))) as p:
        for res in p.imap_unordered(run, syms):
            print(*res, flush=True)
