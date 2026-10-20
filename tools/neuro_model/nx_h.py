"""Neuro — a harness on the deployed scheme's walk-forward scores (nx_sel.py): every hour x side above the year's
threshold (q 0.995 = the bot, q 0.98 = the check set), one trade per coin & side until it exits, at most 12 per side;
exits re-simulated on 1h bars (entry at the next bar's open, the ATR of the features)."""
import glob, os, numpy as np, datetime as dt
from numba import njit
from common import load, D
from mk import ts
import nx_feat
S = np.load(f"{D}/nx_sel.npz")
T, SY, KEEP = S["T"], S["SY"], S["keep"]
files = sorted(glob.glob(f"{D}/nx/*.npz"))
I_all, X_all = [], []
for fn in files:
    z = np.load(fn)
    if len(z["t"]): I_all.append(z["i"]); X_all.append(z["X"])
I = np.concatenate(I_all)[KEEP]
NAMES = nx_feat.NAMES
COLS = ("b_r24", "b_r1", "b_e50", "dd_e200", "adx", "atr_pct", "rsi14", "vol_z", "fund", "roc24")
Xc = np.concatenate(X_all)[KEEP][:, [NAMES.index(c) for c in COLS]]
F = {c: Xc[:, k] for k, c in enumerate(COLS)}
SYMS = [os.path.basename(f)[:-4] for f in files]
YR = np.minimum(np.array([dt.datetime.fromtimestamp(int(t), dt.timezone.utc).year for t in T]), 2025)
def cand(side, q, mask=None):
    sc, thr = S[f"sc{side}"], S[(f"t995_{side}" if q == 0.995 else f"t98_{side}")]
    m = (sc >= thr) & ~np.isnan(sc)
    if mask is not None: m &= mask
    return np.where(m)[0]
BARS = {}
def bars(k):
    if k not in BARS:
        cs = load(SYMS[k]); O = np.array([c["open"] for c in cs]); H = np.array([c["high"] for c in cs]); L = np.array([c["low"] for c in cs]); C = np.array([c["close"] for c in cs])
        atr = np.array([a if a is not None else np.nan for a in nx_feat._wilder(nx_feat._tr(list(H), list(L), list(C)), 14)])
        BARS[k] = (O, H, L, C, atr)
    return BARS[k]
@njit(cache=True)
def sim(O, H, L, C, i, s, a, stop_k, take, hold, close_soft, hard):
    """entry O[i+1]; stop_k ATR on touch (or by the 1h close at close_soft ATR with a hard stop at `hard` ATR); take R of
    the sizing risk's... take = R of stop_k*a (or of close_soft*a); R per the sizing risk"""
    n = len(C); e = O[i + 1]
    soft = (close_soft if hard > 0 else stop_k) * a
    risk = (hard if hard > 0 else stop_k) * a
    hs = e - s * risk; ss = e - s * soft; tp = e + s * take * soft
    W = min(hold, n - i - 1)
    k = W - 1; ex = C[i + k + 1] if i + k + 1 < n else C[n - 1]
    for q in range(W):
        b = i + 1 + q
        if (s > 0 and L[b] <= hs) or (s < 0 and H[b] >= hs):
            ex = hs; k = q; break
        if take > 0 and ((s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp)):
            ex = tp; k = q; break
        if hard > 0 and ((s > 0 and C[b] <= ss) or (s < 0 and C[b] >= ss)):
            ex = C[b]; k = q; break
    return (s * (ex - e) - (0.001 + 0.0003 * (k + 1) / 24) * e) / risk, k + 1
def outcomes(rows, s, stop_k=1.0, take=3.0, hold=48, close_soft=0.0, hard=0.0):
    R = np.full(len(rows), np.nan); K = np.ones(len(rows), np.int64)
    for n_, r in enumerate(rows):
        O, H, L, C, atr = bars(int(SY[r])); i = int(I[r])
        if i + 2 >= len(C) or atr[i] != atr[i]: continue
        R[n_], K[n_] = sim(O, H, L, C, i, s, float(atr[i]), stop_k, take, hold, close_soft, hard)
    return R, K
def build(q, mask=None, sides=(1, -1), **kw):
    """-> list of trades (t, end, r, side, row) after the replay"""
    ev = []
    for s in sides:
        rows = cand(s, q, mask)
        R, K = outcomes(rows, s, **kw)
        sc = S[f"sc{s}"][rows]
        ev += [(int(T[r]), -float(sc[n_]), int(SY[r]), s, float(R[n_]), int(K[n_]), int(r)) for n_, r in enumerate(rows) if R[n_] == R[n_]]
    ev.sort()
    busy, act, out = {}, [], []
    for t, _, sy, s, r, k, row in ev:
        if busy.get((sy, s), 0) > t: continue
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == s) >= 12: continue
        end = t + 3600 * (k + 1); busy[(sy, s)] = end; act.append((end, s)); out.append((t, end, r, s, row))
    return out
rng = np.random.default_rng(3)
def pain(tr, target, grid, nb=250):
    ym = lambda t: t // (30 * 86400)
    bl = {}
    for n_, x in enumerate(tr): bl.setdefault(ym(x[0]), []).append(n_)
    bl = list(bl.values()); best = None
    B = []
    for _ in range(nb):
        ev, base = [], 0
        for z, b in enumerate(rng.choice(len(bl), len(bl))):
            t0 = min(tr[n_][0] for n_ in bl[b])
            for n_ in bl[b]: ev += [(base + tr[n_][0] - t0, 0, n_, (z, n_)), (base + tr[n_][1] - t0, 1, n_, (z, n_))]
            base += 40 * 86400
        B.append(sorted(ev, key=lambda e: (e[0], -e[1])))
    for f in grid:
        xs, ds = [], []
        for ev in B:
            eq, peak, dd, risk = 1.0, 1.0, 0.0, {}
            for _, k, n_, u in ev:
                if k == 0: risk[u] = eq * f
                else:
                    eq += risk.pop(u) * tr[n_][2]; peak = max(peak, eq); dd = max(dd, 1 - eq / peak)
                    if eq <= 0.02: eq, dd = 0.0, 1.0; break
            xs.append(eq); ds.append(dd)
        if np.quantile(ds, .9) <= target: best = (f, float(np.median(xs)), float(np.median(ds)))
        else: break
    return best
def line(nm, tr, q):
    r = np.array([x[2] for x in tr]); t = np.array([x[0] for x in tr]); o = sorted(tr, key=lambda x: x[1])
    run = w = 0
    for x in o: run = run + 1 if x[2] < 0 else 0; w = max(w, run)
    yrs = " ".join(f"{r[(t >= ts(y)) & (t < ts(y + 1))].mean():+.2f}" for y in (2022, 2023, 2024, 2025, 2026))
    target = 0.45 if q == 0.995 else 0.50
    grid = (0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05) if q == 0.995 else (0.001, 0.002, 0.003, 0.005, 0.0075, 0.01, 0.015)
    b = pain(tr, target, grid)
    print(f"{nm:42s} {len(r):5d} {r.mean():+.3f} WR {np.mean(r > 0)*100:3.0f}% подряд {w:2d} | {yrs} | " + (f"{b[0]*100:.2f}%: x{b[1]:.1f} (обычная {b[2]*100:.0f}%)" if b else "—"), flush=True)
