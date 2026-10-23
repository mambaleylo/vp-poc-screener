"""the user's idea (a post): a full 5th Elliott wave, a bearish RSI divergence between the 3rd and the 5th tops, no entry
at the top — wait for the first drop wave, then a short on the bounce into the Fibo zone; the stop beyond the level
where the scenario breaks (the 5th top), the target 0.702 of the impulse (1:3). Mirrored for longs.
Causal: pivots by a zigzag of k x ATR(14) — a pivot is known only once the price came back k ATR from it (its confirm
bar); the setup is checked when the first drop's low A is confirmed; then a limit at A + f x (P5 - A), alive N bars
while the price stays below P5; a fill = the bar's high reaches it (a bar opening beyond fills at its open). The stop at
P5 + 0.1 ATR, the take at P5 - 0.702 x (P5 - P0) (or k R / at A); the stop first in a bar, out after H bars.
Fees: limit in 0.02%, take 0.02%, stop / time 0.05%, funding 0.03% a day. usage: ew5.py TFH (15m: 0.25)"""
import sys; AV = list(sys.argv)
import os, numpy as np, warnings; warnings.filterwarnings("ignore")
from numba import njit
TFH = float(AV[1]) if len(AV) > 1 else 1.0
from common import D as ROOT
import pickle

def load(sym):
    if TFH < 0.1:   # 1m (data/1mz: 40 coins, 2024-10 ..)
        fn = f"{ROOT}/data/1mz/{sym}.npz"
        if not os.path.exists(fn): return None
        z = np.load(fn); return z["t"].astype(np.int64), z["o"], z["h"], z["l"], z["c"]
    if TFH == 0.25:
        fn = f"{ROOT}/data/15m/{sym}.csv"
    else:
        fn = f"{ROOT}/data/1h/{sym}.csv"
    if not os.path.exists(fn): return None
    a = np.loadtxt(fn, delimiter=",", ndmin=2); t = a[:, 0].astype(np.int64)
    k = np.r_[True, np.diff(t) > 0]; a = a[k]; t = a[:, 0].astype(np.int64)
    if TFH in (0.25, 1.0):
        return t, a[:, 1], a[:, 2], a[:, 3], a[:, 4]
    h = int(TFH); blk = t // (h * 3600)
    st = np.r_[0, np.flatnonzero(blk[1:] != blk[:-1]) + 1]; en = np.r_[st[1:], len(t)]
    full = (en - st) == h; st, en = st[full], en[full]
    return (blk[st] * h * 3600, a[st, 1], np.array([a[s:e, 2].max() for s, e in zip(st, en)]),
            np.array([a[s:e, 3].min() for s, e in zip(st, en)]), a[en - 1, 4])

@njit
def wilder(H, L, C, n):
    out = np.full(len(C), np.nan); s = 0.0
    if len(C) <= n: return out
    for i in range(n):
        s += (H[i] - L[i]) if i == 0 else max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1]))
    a = s / n; out[n - 1] = a
    for i in range(n, len(C)):
        a = (a * (n - 1) + max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1]))) / n; out[i] = a
    return out

@njit
def rsi(C, n):
    out = np.full(len(C), 50.0); au = 0.0; ad = 0.0
    for i in range(1, len(C)):
        d = C[i] - C[i - 1]; u = d if d > 0 else 0.0; dn = -d if d < 0 else 0.0
        if i <= n:
            au += u / n; ad += dn / n
        else:
            au = (au * (n - 1) + u) / n; ad = (ad * (n - 1) + dn) / n
        if i >= n: out[i] = 100 - 100 / (1 + au / ad) if ad > 0 else 100.0
    return out

@njit
def zigzag(H, L, atr, k):
    """causal pivots: (bar of the extreme, price, +1 high / -1 low, the bar it was confirmed)"""
    n = len(H); piv_i = []; piv_p = []; piv_t = []; piv_c = []
    d = 0; ei = 20; ep = H[20]
    lo_i = 20; lo_p = L[20]
    for i in range(21, n):
        a = atr[i]
        if not (a > 0): continue
        if d >= 0:   # looking for a high
            if H[i] > ep or d == 0:
                if H[i] > ep: ei = i; ep = H[i]
            if d == 0 and L[i] < lo_p: lo_i = i; lo_p = L[i]
            if ep - L[i] >= k * atr[ei] and (d == 1 or ep - lo_p >= k * atr[ei]):
                piv_i.append(ei); piv_p.append(ep); piv_t.append(1); piv_c.append(i)
                d = -1; ei = i; ep = L[i]
                continue
        if d == -1:
            if L[i] < ep: ei = i; ep = L[i]
            if H[i] - ep >= k * atr[ei]:
                piv_i.append(ei); piv_p.append(ep); piv_t.append(-1); piv_c.append(i)
                d = 1; ei = i; ep = H[i]
        elif d == 1 and False:
            pass
    return np.array(piv_i), np.array(piv_p), np.array(piv_t), np.array(piv_c)

@njit
def trade(O, H, L, C, c0, s, lv, p5, sl_buf, atr_a, tp, wait, hold, fpd):
    """a limit at lv from the bar after c0 for `wait` bars while the price stays on our side of p5 -> (R, took, fb) or fb -1"""
    n = len(C); fb = -1
    for b in range(c0 + 1, min(n, c0 + 1 + wait)):
        if (s < 0 and H[b] >= lv) or (s > 0 and L[b] <= lv):   # the limit reached (a bar through it and past P5 too: filled, then
            fb = b; break                                       # the stop in the same bar — the worst case)
        if (s < 0 and H[b] >= p5) or (s > 0 and L[b] <= p5):   # (never: lv is below P5 for a short) the scenario broke
            return 0.0, 0, -2
    if fb < 0: return 0.0, 0, -1
    fill = max(lv, O[fb]) if s < 0 else min(lv, O[fb])
    sl = p5 - s * sl_buf * atr_a
    risk = abs(fill - sl)
    if risk <= 0: return 0.0, 0, -1
    if s * (tp - fill) <= 0: return 0.0, 0, -1
    e = min(n, fb + hold); ex = C[e - 1]; k = e - 1 - fb; win = 0; fo = 0.0005
    for q in range(e - fb):
        b = fb + q
        if (s < 0 and H[b] >= sl) or (s > 0 and L[b] <= sl):
            gap = (s < 0 and O[b] >= sl) or (s > 0 and O[b] <= sl)
            ex = O[b] if (gap and q > 0) else sl; k = q; break
        if q > 0 and ((s < 0 and L[b] <= tp) or (s > 0 and H[b] >= tp)):
            ex = tp; k = q; win = 1; fo = 0.0002; break
    return (s * (ex - fill) - (0.0002 + fo + 0.0003 * (k + 1) / fpd) * fill) / risk, win, fb

def run(sym, k_zz, out):
    d = load(sym)
    if d is None or len(d[0]) < 500: return
    T, O, H, L, C = d; atr = wilder(H, L, C, 14); r = rsi(C, 14)
    pi, pp, pt, pc = zigzag(H, L, atr, k_zz)
    fpd = 24.0 / TFH
    for j in range(6, len(pi)):
        # the 7 last confirmed pivots: P0..P5 and A (A confirmed at pc[j])
        P = pp[j - 6:j + 1]; I = pi[j - 6:j + 1]; tp_ = pt[j - 6:j + 1]
        for s, sig in ((-1, np.array([-1, 1, -1, 1, -1, 1, -1])), (1, np.array([1, -1, 1, -1, 1, -1, 1]))):
            if not np.array_equal(tp_, sig): continue
            u = -s   # +1 = the impulse went up (a short setup)
            p0, p1, p2, p3, p4, p5, A = P * u   # mirrored: work as if up
            if not (p1 > p0 and p2 > p0 and p3 > p1 and p5 > p3): continue
            w1, w3, w5 = p1 - p0, p3 - p2, p5 - p4
            if w3 < min(w1, w5): continue
            overlap = p4 <= p1
            div = (r[I[5]] < r[I[3]]) if u > 0 else (r[I[5]] > r[I[3]])
            a5 = atr[I[5]]
            c0 = pc[j]
            for f in (0.5, 0.618, 0.705):
                lv = (A + f * (p5 - A)) * u
                if (u > 0 and C[c0] >= lv) or (u < 0 and C[c0] <= lv): continue   # already past the zone at the confirmation
                for tpn, tpv in (("0.702 от P0", (p5 - 0.702 * (p5 - p0)) * u), ("0.702 от P2", (p5 - 0.702 * (p5 - p2)) * u), ("A", A * u)):
                    R_, w, fb = trade(O, H, L, C, c0, s, lv, P[5], 0.1, a5, tpv, 50, 200, fpd)
                    if fb < 0: continue
                    rr = abs(tpv - lv) / max(abs(lv - (P[5] - s * 0.1 * a5)), 1e-12)
                    out.append((sym, int(T[c0]), s, k_zz, f, tpn, bool(div), bool(overlap), float(R_), int(w), float(rr)))

if __name__ == "__main__":
    import multiprocessing as mp
    syms = [l.strip() for l in open("coins127.txt") if l.strip()]
    if TFH < 0.1: syms = sorted(f[:-4] for f in os.listdir(f"{ROOT}/data/1mz"))
    def job(sym):
        o = []
        for kz in (2.0, 3.0, 4.0): run(sym, kz, o)
        return o
    with mp.Pool(2) as p:
        res = [x for r_ in p.map(job, syms) for x in r_]
    pickle.dump(res, open(f"ew5_{TFH}.pkl", "wb"))
    print("events", len(res))
