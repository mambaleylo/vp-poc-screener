"""P/R: more and better trades (the user: "улучшения по количеству и качеству сделок"). The 1h band events of the 211 coins
(prv_ev2.py, with the funding) labelled by the bot's own trade (prx_settle): the limit 0.3 ATR better than the next open
for 3 bars, the stop at an hour's close 3 ATR, the hard stop 6 ATR (R = the hard stop's distance), the take 4.5 ATR,
48 bars. Walk-forward as the deployed scheme: a model per side (LightGBM, the export's settings) every quarter
2023-01 .. 2026-07 on the 24 months before (a 10-day gap), the threshold = the q-quantile of its scores over the last 12
months of its window; one trade a coin & side at a time, at most 20 a side; the BTC filter (24 h 4% / 1 h 1%).
Then: (1) the threshold q; (2) the entry (market / 0.15 ATR / 0.3 ATR for 6 bars); (4) the exits (the take 3 / 6 ATR, 24 / 72
bars, the stops to the entry after +1 x the stop); (5) the BTC filter (off / 3% & 0.7% / 6% & 1.5%). By year 2023-2026.
-> the table, <LABSTORE>/wf/prv_lab.npz (the scores)"""
import os, sys, gzip, glob, time, numpy as np, lightgbm as lgb
from numba import njit
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "neuro_model")); sys.path.insert(0, HERE)
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
import nx_feat
from prv_ev import BAND_NAMES
NAMES = BAND_NAMES + nx_feat.NAMES
IB24, IB1 = NAMES.index("b_r24"), NAMES.index("b_r1")
FEE, FUND = 0.001, 0.0003


def ts(y, m=1):
    import calendar
    return calendar.timegm((y, m, 1, 0, 0, 0))


def load1h(sym):
    a = np.loadtxt(gzip.open(f"{ST}/data/1h/{sym}.csv.gz", "rt"), delimiter=",", usecols=(0, 1, 2, 3, 4))
    _, k = np.unique(a[:, 0], return_index=True); a = a[k]
    return a[:, 0].astype(np.int64), a[:, 1], a[:, 2], a[:, 3], a[:, 4]


@njit(cache=True)
def wilder(H, L, C, n):
    m = len(C); out = np.full(m, np.nan); tr = np.empty(m); tr[0] = H[0] - L[0]
    for i in range(1, m):
        tr[i] = max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1]))
    if m >= n:
        a = tr[:n].mean(); out[n - 1] = a
        for i in range(n, m):
            a = (a * (n - 1) + tr[i]) / n; out[i] = a
    return out


@njit(cache=True)
def walk(O, H, L, C, i, s, a, lim, wait, soft_x, hard_x, take_x, hold, be_x):
    """the bot's P/R trade of the event closing bar i (prx_settle) -> (R by the hard stop, bars to the exit from the event) or
    (nan, bars) for no fill; be_x > 0: after the price went be_x x the soft stop, the stops at the entry"""
    n = len(C)
    if i + 1 >= n:
        return np.nan, -1
    o0 = O[i + 1]
    k0 = -1; e = 0.0
    if lim > 0:
        lv = o0 - s * lim * a
        for k in range(wait):
            j = i + 1 + k
            if j >= n:
                return np.nan, -1
            if (L[j] <= lv) if s > 0 else (H[j] >= lv):
                k0 = k; e = min(lv, O[j]) if s > 0 else max(lv, O[j]); break
        if k0 < 0:
            return np.nan, wait
    else:
        k0 = 0; e = o0
    soft = soft_x * a; hard = hard_x * a
    sl = e - s * soft; hs = e - s * hard; tp = e + s * take_x * a
    took = False
    for k in range(hold):
        j = i + 1 + k0 + k
        if j >= n:
            return np.nan, -1
        if (L[j] <= hs) if s > 0 else (H[j] >= hs):
            ex = hs
            return (s * (ex - e) - e * FEE - e * FUND * (k + 1) / 24) / hard, k0 + k + 1
        if (H[j] >= tp) if s > 0 else (L[j] <= tp):
            return (s * (tp - e) - e * FEE - e * FUND * (k + 1) / 24) / hard, k0 + k + 1
        if be_x > 0 and not took and ((H[j] - e) if s > 0 else (e - L[j])) >= be_x * soft:
            took = True; hs = e; sl = e
        if (C[j] <= sl) if s > 0 else (C[j] >= sl):
            return (s * (C[j] - e) - e * FEE - e * FUND * (k + 1) / 24) / hard, k0 + k + 1
    j = i + k0 + hold
    if j >= n:
        return np.nan, -1
    return (s * (C[j] - e) - e * FEE - e * FUND * hold / 24) / hard, k0 + hold


VAR = {"сейчас": (0.3, 3, 3.0, 6.0, 4.5, 48, 0.0),
       "вход по рынку": (0.0, 1, 3.0, 6.0, 4.5, 48, 0.0), "вход 0.15 ATR": (0.15, 3, 3.0, 6.0, 4.5, 48, 0.0), "вход 0.3 ATR, ждать 6 ч": (0.3, 6, 3.0, 6.0, 4.5, 48, 0.0),
       "тейк 3 ATR": (0.3, 3, 3.0, 6.0, 3.0, 48, 0.0), "тейк 6 ATR": (0.3, 3, 3.0, 6.0, 6.0, 48, 0.0),
       "держать 24 ч": (0.3, 3, 3.0, 6.0, 4.5, 24, 0.0), "держать 72 ч": (0.3, 3, 3.0, 6.0, 4.5, 72, 0.0),
       "безубыток после +3 ATR": (0.3, 3, 3.0, 6.0, 4.5, 48, 1.0), "безубыток после +1.5 ATR": (0.3, 3, 3.0, 6.0, 4.5, 48, 0.5)}
BTCF = {"фильтр BTC 4% / 1% (сейчас)": (4.0, 1.0), "без фильтра BTC": (99.0, 99.0), "фильтр BTC 3% / 0.7%": (3.0, 0.7), "фильтр BTC 6% / 1.5%": (6.0, 1.5)}
QS = (0.99, 0.985, 0.98, 0.97)
P = dict(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1, colsample_bytree=0.5,
         reg_lambda=10.0, verbose=-1, n_jobs=4)


def build():
    """the 1h events, their bars, every variant's label"""
    Xs, Ts, Ss, Cs, Ls, Bs = [], [], [], [], [], []
    files = sorted(glob.glob(f"{ST}/prv_ev/*.npz"))
    for ci, fn in enumerate(files):
        z = np.load(fn); X = z["X"]; t = z["t"]
        if not len(t): continue
        m = X[:, 0] == 1
        X, t = X[m], t[m]
        T, O, H, L, C = load1h(os.path.basename(fn)[:-4]); A = wilder(H, L, C, 14)
        idx = np.searchsorted(T, t - 3600)
        ok = (idx < len(T)) & (T[np.minimum(idx, len(T) - 1)] == t - 3600)
        X, t, idx = X[ok], t[ok], idx[ok]
        lab = np.full((len(t), len(VAR)), np.nan, np.float32); bars = np.zeros((len(t), len(VAR)), np.int32)
        for k in range(len(t)):
            i = idx[k]; s = int(X[k, 1]); a = A[i]
            if not a == a: continue
            for vi, v in enumerate(VAR.values()):
                lab[k, vi], bars[k, vi] = walk(O, H, L, C, i, s, a, *v)
        Xs.append(X); Ts.append(t); Ss.append(np.full(len(t), ci, np.int16)); Ls.append(lab); Bs.append(bars)
        print(f"{os.path.basename(fn)[:-4]} {len(t)}", flush=True)
    return np.concatenate(Xs), np.concatenate(Ts), np.concatenate(Ss), np.concatenate(Ls), np.concatenate(Bs)


def replay(sel, T, SY, SD, R, B, cap=20):
    o = sel[np.argsort(T[sel], kind="stable")]
    busy, act, out = {}, [], []
    for j in o:
        if not R[j] == R[j] and B[j] <= 0: continue
        t = T[j]; key = (SY[j], SD[j])
        if busy.get(key, 0) > t: continue
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == SD[j]) >= cap: continue
        end = t + max(int(B[j]), 1) * 3600
        busy[key] = end
        if R[j] == R[j]:
            act.append((end, SD[j])); out.append((t, float(R[j])))
    return out


if __name__ == "__main__":
    t0 = time.time()
    fn = f"{ST}/wf/prv_lab_ev.npz"
    if os.path.exists(fn):
        z = np.load(fn); X, T, SY, LAB, BAR = z["X"], z["T"], z["SY"], z["LAB"], z["BAR"]
    else:
        X, T, SY, LAB, BAR = build(); np.savez(fn, X=X, T=T, SY=SY, LAB=LAB, BAR=BAR)
    SD = X[:, 1].astype(int)
    print(f"1h events {len(T)}, built in {time.time() - t0:.0f}s", flush=True)
    lab = LAB[:, 0]   # the deployed rule: what the models learn
    SC = np.full(len(T), np.nan); THR = {}
    QT = [(y, m) for y in range(2023, 2027) for m in (1, 4, 7, 10) if (y, m) <= (2026, 7)]
    for (y, m) in QT:
        a0 = ts(y, m); a1 = ts(y + (m + 3 > 12), (m + 3 - 1) % 12 + 1)
        tr = (T >= a0 - 730 * 86400) & (T < a0 - 10 * 86400)
        ref = (T >= a0 - 365 * 86400) & (T < a0 - 10 * 86400)
        te = (T >= a0) & (T < a1)
        for s in (1, -1):
            ok = tr & (SD == s) & np.isfinite(lab)
            md = lgb.LGBMRegressor(random_state=1, **P).fit(X[ok], np.clip(lab[ok], -1.5, 2.0))
            w = (SD == s) & (ref | te)
            p = md.predict(X[w]); sc = np.full(len(T), np.nan); sc[w] = p
            SC[te & (SD == s)] = sc[te & (SD == s)]
            for q in QS:
                THR[(y, m, s, q)] = float(np.nanquantile(sc[ref & (SD == s)], q))
        print(f"квартал {y}-{m:02d} готов ({time.time() - t0:.0f}s)", flush=True)
    np.savez(f"{ST}/wf/prv_lab.npz", SC=SC, T=T)
    YRS = (2023, 2024, 2025, 2026); WK = {2023: 52, 2024: 52, 2025: 52, 2026: 39}
    yr = np.array([int(1970 + (t / 86400 + 0.5) / 365.2425) for t in T])
    thr_of = np.full((len(T), len(QS)), np.inf)
    for (y, m) in QT:
        a0 = ts(y, m); a1 = ts(y + (m + 3 > 12), (m + 3 - 1) % 12 + 1); te = (T >= a0) & (T < a1)
        for s in (1, -1):
            for qi, q in enumerate(QS):
                thr_of[te & (SD == s), qi] = THR[(y, m, s, q)]

    def row(name, qi, vi, bf):
        b24, b1 = X[:, IB24], X[:, IB1]
        okb = ~((SD * b24 <= -bf[0]) | (SD * b1 <= -bf[1]))
        sel = np.flatnonzero(np.isfinite(SC) & (SC >= thr_of[:, qi]) & okb)
        out = replay(sel, T, SY, SD, LAB[:, vi], BAR[:, vi])
        cells = []
        for Y in YRS:
            r = [x for t, x in out if int(1970 + (t / 86400 + 0.5) / 365.2425) == Y]
            cells.append(f"{np.mean(r):+.2f}R {len(r) / WK[Y]:.1f}/нед" if r else "—")
        allr = [x for _, x in out]
        print(f"{name:34s} | " + " | ".join(cells) + f" | всего {np.mean(allr):+.3f}R, {len(allr)} сделок, R в неделю {np.sum(allr) / (sum(WK.values())):.2f}", flush=True)
    base = list(BTCF.values())[0]
    print("\n(1) порог отбора — вариант | 2023 | 2024 | 2025 | 2026 (по сен) | итого", flush=True)
    for qi, q in enumerate(QS):
        row(f"лучшие {100 - q * 100:.1f}%", qi, 0, base)
    print("\n(2, 4) вход и выходы (порог 1%)", flush=True)
    for vi, v in enumerate(VAR):
        row(v, 0, vi, base)
    print("\n(5) фильтр BTC (порог 1%)", flush=True)
    for nm, bf in BTCF.items():
        row(nm, 0, 0, bf)
    print("prv lab done", flush=True)
