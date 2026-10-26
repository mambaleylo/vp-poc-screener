"""Cross-sectional momentum / reversal (freqtrade-style rank pairlists, the crypto momentum factor papers): every
Monday 00:00 UTC rank the coins (>= 90 days of history, top-150 by 30-day quote volume) by the return over the last L
days (skipping the last S days), long the top N, short the bottom N, equal weight, hold 7 days (close to close at
the 1h closes, i.e. entry at the rank time's price -- the rank uses only bars closed before it). Fees 0.1% per side on
the traded notional (turnover), funding: the real 8h funding of each coin from data/funding (longs pay, shorts get).
Gross 1x (0.5 long + 0.5 short). Output per variant: CAGR, maxDD, Sharpe (weekly), by year."""
import numpy as np, json, os, glob
from lv_engine import load_np
sp = json.load(open("lv/split.json")); syms = sp["bot"] + sp["chk"]; BOT = set(sp["bot"])
T0 = 1577836800; TW = 7 * 86400
t_mon = np.arange(1578268800, 1792000000, TW)   # Mondays 00:00 UTC from 2020-01-06
closes = np.full((len(syms), len(t_mon)), np.nan); qv30 = np.full_like(closes, np.nan); age = np.zeros_like(closes)
daily = {}
for k, s in enumerate(syms):
    T, O, H, L, C, V = load_np(s)
    # the last close strictly before each Monday 00:00 = the close of the 23:00 bar
    j = np.searchsorted(T, t_mon) - 1   # bar index with T < t_mon
    ok = (j >= 0) & (j < len(T)) & (T[np.clip(j, 0, len(T) - 1)] >= t_mon - 3 * 3600)
    closes[k, ok] = C[j[ok]]
    cv = np.cumsum(np.insert(V, 0, 0.0)); jj = np.clip(j + 1, 0, len(T)); j30 = np.searchsorted(T, t_mon - 30 * 86400)
    qv30[k, ok] = (cv[jj] - cv[j30])[ok]
    age[k] = (t_mon - T[0]) / 86400
    # daily closes for the lookback with a skip
    daily[k] = (T, C)
fund = {}
for k, s in enumerate(syms):
    fn = f"data/funding/{s}.csv"
    if os.path.exists(fn):
        a = np.loadtxt(fn, delimiter=",", ndmin=2)
        if len(a): fund[k] = (a[:, 0].astype(np.int64) // (1000 if a[0, 0] > 1e11 else 1), a[:, 1])
def fsum(k, t0, t1):
    if k not in fund: return 0.0
    tt, rr = fund[k]; m = (tt >= t0) & (tt < t1); return rr[m].sum()
def past_ret(k, t, L, S):
    T, C = daily[k]
    a = np.searchsorted(T, t - L * 86400) - 1; b = np.searchsorted(T, t - S * 86400) - 1
    if a < 0 or b < 0 or b <= a: return np.nan
    return C[b] / C[a] - 1
def run(L, S, N, sign, legs="ls", sub=None):
    w_prev = {}; eq = [1.0]; rets = []; tt = []
    for i in range(len(t_mon) - 1):
        t = t_mon[i]
        if t < 1609459200 - 0: continue   # from 2021 (enough coins listed)
        elig = [k for k in range(len(syms)) if age[k, i] >= 90 and np.isfinite(closes[k, i]) and np.isfinite(closes[k, i + 1])
                and (sub is None or (syms[k] in BOT) == sub)]
        if len(elig) < 4 * N: continue
        elig = sorted(elig, key=lambda k: -qv30[k, i])[:150]
        r = np.array([past_ret(k, t, L, S) for k in elig]); m = np.isfinite(r)
        el = np.array(elig)[m]; r = r[m]
        o = np.argsort(-sign * r)
        lo, sh = el[o[:N]], el[o[-N:]]
        w = {}
        if "l" in legs:
            for k in lo: w[k] = w.get(k, 0) + (0.5 if legs == "ls" else 1.0) / N
        if "s" in legs:
            for k in sh: w[k] = w.get(k, 0) - (0.5 if legs == "ls" else 1.0) / N
        turn = sum(abs(w.get(k, 0) - w_prev.get(k, 0)) for k in set(w) | set(w_prev))
        pr = sum(wk * (closes[k, i + 1] / closes[k, i] - 1) for k, wk in w.items())
        fd = sum(-wk * fsum(k, t, t_mon[i + 1]) for k, wk in w.items())
        r_ = pr + fd - 0.001 * turn
        # drift the weights to the week's end for the next turnover
        w_prev = {k: wk * closes[k, i + 1] / closes[k, i] for k, wk in w.items()}
        rets.append(r_); tt.append(t)
    rets = np.array(rets); tt = np.array(tt)
    eq = np.cumprod(1 + rets); dd = (1 - eq / np.maximum.accumulate(eq)).max()
    yrs = len(rets) / 52.18; cagr = eq[-1] ** (1 / yrs) - 1
    sh = rets.mean() / rets.std() * np.sqrt(52.18) if rets.std() > 0 else 0
    yy = {Y: np.prod(1 + rets[(tt >= np.datetime64(f"{Y}-01-01").astype("datetime64[s]").astype(int)) & (tt < np.datetime64(f"{Y+1}-01-01").astype("datetime64[s]").astype(int))]) - 1 for Y in range(2021, 2027)}
    return cagr, dd, sh, yy
print("funding coins", len(fund), flush=True)
for nm, sign, LS in (("моментум", 1, ((28, 0), (28, 7), (56, 7), (90, 7), (14, 0), (7, 0))), ("разворот", -1, ((1, 0), (3, 0), (7, 0)))):
    for L, S in LS:
        for N in (10, 20):
            for legs in ("ls", "l", "s"):
                c, d, s_, yy = run(L, S, N, sign, legs)
                print(f"{nm:8s} L{L:3d} S{S} N{N} {legs:2s}: CAGR {c*100:+6.0f}% DD {d*100:4.0f}% Sharpe {s_:+.2f} | " + " ".join(f"{Y%100}:{v*100:+.0f}%" for Y, v in yy.items()), flush=True)
