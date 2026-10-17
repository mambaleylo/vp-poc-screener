"""Peak Reversal audit — the rule grid on Binance history (no model): for every coin, chart (1h / 4h), basis
(EMA14 / EMA20 / EMA30 / SMA20), band (1.5 / 2 / 2.5 / 3 ATR), entry type (wick touch = the bot's, close beyond the
band, close back inside after a close beyond) and every stop x take x hold: trades one at a time per coin & rule
(as the bot), entry at the next bar's open, stop first, fee 0.1% + funding 0.03%/day.
Saved per coin: monthly n / sum R / wins per (config, label) -> pooled tables later."""
import sys, os, time
ARGS = sys.argv[1:]
import numpy as np
from common import V, load, D
import multiprocessing as mp
TFS = {"1h": 1, "4h": 4}
BASES = [("EMA", 14), ("EMA", 20), ("EMA", 30), ("SMA", 20)]
MULTS = (1.5, 2.0, 2.5, 3.0)
KINDS = ("wick", "close", "reent")
STOPS = (1.0, 1.5, 2.0, "ext")      # ATR multiples; ext = beyond the signal bar's extreme + 0.2 ATR
TAKES = (1.0, 1.5, 2.0, 3.0, 4.0, "mid")   # R multiples; mid = back to the basis
HOLDS = (24, 48)                    # bars
FEE, FUND = 0.001, 0.0003
M0 = 2020 * 12   # month index base
NM = 7 * 12
CONFIGS = [(tf, b, m, k) for tf in TFS for b in BASES for m in MULTS for k in KINDS]
LABELS = [(s, t, h) for s in STOPS for t in TAKES for h in HOLDS]

def month_idx(t):
    import datetime as dt
    d = dt.datetime.utcfromtimestamp(int(t))
    return d.year * 12 + d.month - 1 - M0

def run(sym):
    fn = f"{D}/prv/{sym}.npz"
    if os.path.exists(fn):
        return sym, -1
    t0 = time.time()
    h1 = load(sym)
    if not h1 or len(h1) < 24 * 60:
        return sym, 0
    # [config, label, month] -> n, sum, wins ; also per-trade rows of the canonical configs for the model step
    N = np.zeros((len(CONFIGS), len(LABELS), NM), dtype=np.int32)
    S = np.zeros((len(CONFIGS), len(LABELS), NM), dtype=np.float32)
    W = np.zeros((len(CONFIGS), len(LABELS), NM), dtype=np.int32)
    ci = 0
    for tf, hrs in TFS.items():
        cs = h1 if hrs == 1 else V._oc_agg(h1, hrs)
        n = len(cs)
        O = np.array([c["open"] for c in cs]); H = np.array([c["high"] for c in cs]); L = np.array([c["low"] for c in cs]); C = np.array([c["close"] for c in cs])
        T = np.array([c["time"] for c in cs])
        atr = np.array([a if a else np.nan for a in V.neuro_atr_series(cs, 14)], dtype=float)
        mon = np.array([month_idx(t) for t in T])
        for (mt, ln) in BASES:
            basis = np.array([b if b is not None else np.nan for b in V.prv_ma_series(cs, mt, ln)], dtype=float)
            for mult in MULTS:
                up, dn = basis + atr * mult, basis - atr * mult
                for kind in KINDS:
                    if kind == "wick":
                        sh = H >= up; lo = (L <= dn) & ~sh
                    elif kind == "close":
                        sh = C >= up; lo = C <= dn
                    else:
                        prev_up = np.concatenate([[False], C[:-1] >= up[:-1]]); prev_dn = np.concatenate([[False], C[:-1] <= dn[:-1]])
                        sh = prev_up & (C < up); lo = prev_dn & (C > dn)
                    side = np.where(sh, -1, np.where(lo, 1, 0))
                    side[:ln + 14] = 0
                    side[np.isnan(basis) | np.isnan(atr)] = 0
                    idx = np.where(side != 0)[0]
                    idx = idx[idx < n - 1]
                    # outcomes per signal per label: (r, exit index)
                    R = np.full((len(idx), len(LABELS)), np.nan); X = np.zeros((len(idx), len(LABELS)), dtype=np.int64)
                    for q, i in enumerate(idx):
                        s = side[i]; e = O[i + 1]; a = atr[i]
                        w_end = min(n, i + 1 + max(HOLDS))
                        Hs, Ls, Cs = H[i + 1:w_end], L[i + 1:w_end], C[i + 1:w_end]
                        for li, (sk, tk, hd) in enumerate(LABELS):
                            if sk == "ext":
                                ext = H[i] if s < 0 else L[i]
                                stop = ext - s * 0.2 * a
                            else:
                                stop = e - s * sk * a
                            risk = (e - stop) * s
                            if risk <= e * 0.001:
                                continue
                            if tk == "mid":
                                tp = basis[i]
                                if (tp - e) * s <= 0:
                                    continue
                            else:
                                tp = e + s * tk * risk
                            lim = min(len(Hs), hd)
                            if lim < hd:
                                continue
                            hs = (Ls[:lim] <= stop) if s > 0 else (Hs[:lim] >= stop)
                            ht = (Hs[:lim] >= tp) if s > 0 else (Ls[:lim] <= tp)
                            ks = int(np.argmax(hs)) if hs.any() else 10 ** 6
                            kt = int(np.argmax(ht)) if ht.any() else 10 ** 6
                            if ks <= kt and ks < lim:
                                k, ex = ks, stop
                            elif kt < lim:
                                k, ex = kt, tp
                            else:
                                k, ex = lim - 1, Cs[lim - 1]
                            R[q, li] = (s * (ex - e) - e * FEE - e * FUND * (k + 1) * hrs / 24) / risk
                            X[q, li] = i + 1 + k
                    for li in range(len(LABELS)):
                        busy = -1
                        for q, i in enumerate(idx):
                            if i <= busy or R[q, li] != R[q, li]:
                                continue
                            busy = X[q, li]
                            mm = mon[X[q, li]]
                            if 0 <= mm < NM:
                                N[ci, li, mm] += 1; S[ci, li, mm] += R[q, li]; W[ci, li, mm] += R[q, li] > 0
                    ci += 1
    os.makedirs(f"{D}/prv", exist_ok=True)
    np.savez_compressed(fn, N=N, S=S, W=W)
    return sym, int(N.sum()), round(time.time() - t0)

if __name__ == "__main__":
    syms = ARGS or sorted(f[:-4] for f in os.listdir(f"{D}/data/1h"))
    with mp.Pool(int(os.environ.get("NP", 4))) as p:
        for res in p.imap_unordered(run, syms):
            print(*res, flush=True)
