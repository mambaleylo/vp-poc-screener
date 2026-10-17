"""Range breakout on 4h / 8h / 12h / 1d: range N bars narrower than K x ATR100, a close out of it; gates (own EMA200 of
the chart, the daily EMA200), stops, takes / trailing / breakeven exits; + the 89 Neuro features of the 1h bar
closing with the signal (for the Neuro filters). Per coin and chart: events, features, outcomes."""
import sys, os, time, pickle
ARGS = sys.argv[1:]
import numpy as np
from common import V, load, D
import nx_feat
from nx_build import funding
import multiprocessing as mp
from ev_engine import ema, sma, rmax, rmin
TFH = int(os.environ.get("TFH", 4))
NS = (20, 30, 50) if TFH < 24 else (15, 20, 30)
KMAX = 4.0
STOPS = (1.0, 1.5, 2.0)
EXITS = ("t2", "t3", "t5", "t8", "dc10", "dc20", "dc50", "ch5", "be1dc20", "be1dc50", "half2dc20")
HOLD = int(180 * 24 / TFH) if TFH < 24 else 180
FEE, FUND = 0.001, 0.0003
_REF = {}
def ref():
    if not _REF:
        _REF["btc"], _REF["eth"] = load("BTCUSDT"), load("ETHUSDT")
    return _REF

def outcomes(O, H, L, C, i, s, a, DC):
    n = len(C)
    y = np.full((len(STOPS), len(EXITS), 2), np.nan, dtype=np.float32)
    e = O[i + 1]
    Hm = min(HOLD, n - i - 1)
    if Hm < HOLD:
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
            return ((s * (ex - e) - e * FEE - e * FUND * (j + 1) * TFH / 24) / risk, j + 1)
        def dc_exit(N, start=0):
            lv = DC[N][0][seg] if s > 0 else DC[N][1][seg]
            cond = (Cs < lv) if s > 0 else (Cs > lv)
            cond[:start] = False
            return int(np.argmax(cond)) if cond.any() else Hm
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
                    y[si, xi] = fin(Hm - 1, Cs[-1])
            elif xn.startswith("ch"):
                k = float(xn[2:])
                if s > 0:
                    lvl = np.maximum(stop, np.concatenate([[stop], np.maximum.accumulate(Cs)[:-1] - k * a])); hit = Ls <= lvl
                else:
                    lvl = np.minimum(stop, np.concatenate([[stop], np.minimum.accumulate(Cs)[:-1] + k * a])); hit = Hs >= lvl
                if hit.any():
                    j = int(np.argmax(hit)); px = lvl[j] if j == 0 else (min(Os[j], lvl[j]) if s > 0 else max(Os[j], lvl[j]))
                    y[si, xi] = fin(j, px)
                else:
                    y[si, xi] = fin(Hm - 1, Cs[-1])
            elif xn.startswith("dc"):
                jd = dc_exit(int(xn[2:]))
                if js <= jd and js < Hm:
                    y[si, xi] = fin(js, stop)
                elif jd < Hm:
                    y[si, xi] = fin(jd, Cs[jd])
                else:
                    y[si, xi] = fin(Hm - 1, Cs[-1])
            elif xn.startswith("be1"):
                # after +1R touched the stop moves to the entry (from the next bar on), then the Donchian exit
                N = int(xn[5:])
                ht = (Hs >= e + s * risk) if s > 0 else (Ls <= e + s * risk)
                jb = int(np.argmax(ht)) if ht.any() else Hm
                jd = dc_exit(N)
                if js <= jb and js <= jd and js < Hm:
                    y[si, xi] = fin(js, stop); continue
                if jd < jb and jd < Hm:
                    y[si, xi] = fin(jd, Cs[jd]); continue
                if jb >= Hm:
                    y[si, xi] = fin(Hm - 1, Cs[-1]); continue
                hb = (Ls[jb + 1:] <= e) if s > 0 else (Hs[jb + 1:] >= e)
                jbe = jb + 1 + int(np.argmax(hb)) if hb.any() else Hm
                if jbe <= jd and jbe < Hm:
                    y[si, xi] = fin(jbe, e)
                elif jd < Hm:
                    y[si, xi] = fin(jd, Cs[jd])
                else:
                    y[si, xi] = fin(Hm - 1, Cs[-1])
            else:   # half2dc20: half off at +2R (then the stop to the entry), the rest by the Donchian 20 exit
                ht = (Hs >= e + s * 2 * risk) if s > 0 else (Ls <= e + s * 2 * risk)
                jt = int(np.argmax(ht)) if ht.any() else Hm
                jd = dc_exit(20)
                if js <= jt and js <= jd and js < Hm:
                    y[si, xi] = fin(js, stop); continue
                if jd < jt and jd < Hm:
                    y[si, xi] = fin(jd, Cs[jd]); continue
                if jt >= Hm:
                    y[si, xi] = fin(Hm - 1, Cs[-1]); continue
                hb = (Ls[jt + 1:] <= e) if s > 0 else (Hs[jt + 1:] >= e)
                jbe = jt + 1 + int(np.argmax(hb)) if hb.any() else Hm
                jd2 = dc_exit(20, jt + 1)
                if jbe <= jd2 and jbe < Hm:
                    j2, ex2 = jbe, e
                elif jd2 < Hm:
                    j2, ex2 = jd2, Cs[jd2]
                else:
                    j2, ex2 = Hm - 1, Cs[-1]
                r1 = (2 * risk * 1.0 - e * FEE / 2) / risk
                r2 = (s * (ex2 - e) - e * FEE / 2 - e * FUND * (j2 + 1) * TFH / 24) / risk
                y[si, xi] = (0.5 * r1 + 0.5 * r2, j2 + 1)
    return y

def run(sym):
    fn = f"{D}/rbtf{TFH}/{sym}.pkl"
    if os.path.exists(fn):
        return sym, -1
    t0 = time.time()
    h1 = load(sym)
    if not h1 or len(h1) < 24 * 300:
        return sym, 0
    R_ = ref()
    h4, d1 = V._oc_agg(h1, 4), V._oc_agg(h1, 24)
    rows = nx_feat.nx_series(h1, h4, d1, V.emw_bars(d1, "1w"), R_["btc"], R_["eth"], funding(sym))
    h1_end = np.array([c["time"] + 3600 for c in h1])
    cs = V._oc_agg(h1, TFH) if TFH > 1 else h1
    O = np.array([c["open"] for c in cs]); H = np.array([c["high"] for c in cs]); L = np.array([c["low"] for c in cs]); C = np.array([c["close"] for c in cs])
    T = np.array([c["time"] + TFH * 3600 for c in cs])
    tr = np.array(nx_feat._tr(list(H), list(L), list(C)))
    atr = np.array([v if v is not None else np.nan for v in nx_feat._wilder(list(tr), 14)])
    atr100 = sma(tr, 100)
    e200 = ema(C, 200)
    DC = {N: (rmin(L, N), rmax(H, N)) for N in (10, 20, 50)}
    i_dd = nx_feat.NAMES.index("dd_e200")
    out = []
    for N in NS:
        hh, ll = rmax(H, N), rmin(L, N)
        for i in range(max(N, 210), len(C) - 1):
            if np.isnan(atr[i]) or np.isnan(atr100[i]):
                continue
            s = 1 if (C[i] > hh[i] and C[i - 1] <= hh[i - 1]) else (-1 if (C[i] < ll[i] and C[i - 1] >= ll[i - 1]) else 0)
            rg = (hh[i] - ll[i]) / atr100[i]
            if not s or rg >= KMAX:
                continue
            k1 = np.searchsorted(h1_end, T[i], side="right") - 1
            if k1 < 0 or rows[k1] is None:
                continue
            row = rows[k1]
            f = {"N": N, "rg": rg, "own200": s * (C[i] - e200[i]) > 0, "d200": s * row[i_dd] > 0,
                 "brk": s * (C[i] - (hh[i] if s > 0 else ll[i])) / atr[i], "k1": int(k1)}
            out.append((int(T[i]), s, f, np.array(row, dtype=np.float32), outcomes(O, H, L, C, i, s, atr[i], DC)))
    os.makedirs(f"{D}/rbtf{TFH}", exist_ok=True)
    pickle.dump(out, open(fn, "wb"))
    return sym, len(out), round(time.time() - t0)

if __name__ == "__main__":
    syms = ARGS or sorted(f[:-4] for f in os.listdir(f"{D}/data/1h"))
    with mp.Pool(int(os.environ.get("NP", 4))) as p:
        for res in p.imap_unordered(run, syms):
            print(*res, flush=True)
