"""💪 strong zones, the EMA lesson (a deep quick wick is the best fill): the bot's 2-leg ladder (fastsim.ladder semantics:
fills at the limit or the open after a gap, the stop first incl. the fill bar, the take only against earlier fills;
14 days) with the legs moved: leg = near − p × the zone's width − x daily ATR (then the 0.2% offset), and the limits
kept only `wait` hours after the scan. Stop 1.0 daily ATR past the far edge, take 4R from the average (deployed).
Bot set q 0.95, check q 0.85."""
import numpy as np
from numba import njit
import zm_h as Z
from common import load
d = Z.d
LO, HI, DATR = d.lo.values.astype(float), d.hi.values.astype(float), d.datr_raw.values.astype(float)
@njit(cache=True)
def lad(O, H, L, C, i, s, near, far, da, p1, x1, p2, x2, off, buf, tk, wait, n_max):
    n = min(len(C), i + n_max); W = abs(near - far)
    l1 = (near - s * (p1 * W + x1 * da)) * (1 + s * off / 100); l2 = (near - s * (p2 * W + x2 * da)) * (1 + s * off / 100)
    sl = far - s * buf * da
    if (s > 0 and (l1 <= sl or l2 <= sl)) or (s < 0 and (l1 >= sl or l2 >= sl)): return np.nan, 0
    f1 = 0.0; f2 = 0.0; n1 = False; n2 = False
    for b in range(i, n):
        p1f = n1; p2f = n2; avg = (f1 + f2) / 2 if n2 else f1
        if b - i < wait:
            if not n1 and ((s > 0 and L[b] <= l1) or (s < 0 and H[b] >= l1)):
                n1 = True; f1 = min(l1, O[b]) if s > 0 else max(l1, O[b])
            if n1 and not n2 and ((s > 0 and L[b] <= l2) or (s < 0 and H[b] >= l2)):
                n2 = True; f2 = min(l2, O[b]) if s > 0 else max(l2, O[b])
        if not n1: continue
        if (s > 0 and L[b] <= sl) or (s < 0 and H[b] >= sl):
            ex = O[b] if ((s > 0 and O[b] <= sl) or (s < 0 and O[b] >= sl)) else sl
            g = s * (ex - f1) + (s * (ex - f2) if n2 else 0.0); fee = 0.001 * (f1 + (f2 if n2 else 0.0))
            return (g - fee) / (s * (l1 - sl) + s * (l2 - sl)), b - i + 1
        if p1f:
            tp = avg + s * tk * abs(avg - sl)
            if (s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp):
                g = s * (tp - f1) + (s * (tp - f2) if p2f else 0.0); fee = 0.001 * (f1 + (f2 if p2f else 0.0))
                return (g - fee) / (s * (l1 - sl) + s * (l2 - sl)), b - i + 1
    if not n1: return np.nan, 0
    ex = C[n - 1]; g = s * (ex - f1) + (s * (ex - f2) if n2 else 0.0); fee = 0.001 * (f1 + (f2 if n2 else 0.0))
    return (g - fee) / (s * (l1 - sl) + s * (l2 - sl)), n - i
def labels(idx, p1=0.0, x1=0.0, p2=1.0, x2=0.0, off=0.2, buf=1.0, tk=4.0, wait=336):
    R = np.full(len(d), np.nan); Hh = np.full(len(d), 24.0); cache = {}
    for k in idx:
        sym = Z.SYM[k]
        if sym not in cache:
            cs = load(sym); cache.clear()
            cache[sym] = ({c["time"]: n for n, c in enumerate(cs)}, np.array([c["open"] for c in cs]), np.array([c["high"] for c in cs]),
                          np.array([c["low"] for c in cs]), np.array([c["close"] for c in cs]))
        pos, O, H, L, C = cache[sym]; i = pos.get(int(Z.T[k]))
        if i is None: continue
        s = int(Z.SIDE[k]); near, far = (HI[k], LO[k]) if s > 0 else (LO[k], HI[k])
        r, h = lad(O, H, L, C, i, s, near, far, DATR[k] / 100 * far, p1, x1, p2, x2, off, buf, tk, wait, 336)
        R[k], Hh[k] = r, max(1, h)
    return R, Hh
from zm_x2 import replay
if __name__ == "__main__":
    srt = lambda a: a[np.argsort(Z.SYM[a], kind="stable")]
    all_idx = srt(Z.cand(0.85))
    V = [("сейчас: ближняя + дальняя", dict()), ("обе на дальней", dict(p1=1.0)), ("¾ зоны + дальняя", dict(p1=0.75)),
         ("обе на дальней + 0.1 ATR", dict(p1=1.0, x1=0.1, x2=0.1)), ("дальняя, без отступа 0.2%", dict(p1=1.0, off=0.0)),
         ("дальняя, стоп 0.75 ATR", dict(p1=1.0, buf=0.75)), ("дальняя, стоп 1.25 ATR", dict(p1=1.0, buf=1.25)), ("дальняя, стоп 1.5 ATR", dict(p1=1.0, buf=1.5)),
         ("дальняя, тейк 3R", dict(p1=1.0, tk=3.0)), ("дальняя, тейк 5R", dict(p1=1.0, tk=5.0)), ("дальняя, тейк 6R", dict(p1=1.0, tk=6.0))]
    for nm, kw in V:
        R, Hh = labels(all_idx, **kw)
        for q in (0.95, 0.85):
            for seed in (5, 6):
                Z.rng = np.random.default_rng(seed); tr = replay(Z.cand(q), R, Hh); Z.line(f"{nm[:30]} q{q} s{seed}", tr, q)
