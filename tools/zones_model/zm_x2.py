"""strong zones — the entry by the reaction (the user: "зоны из паблика иногда просто закладываются фитилем и уже идёт
отскок; от наших не видно реакции"): instead of the blind ladder, wait for a 1h candle that dips into the zone and
closes back out (a rejection), enter at the next open; stop past the reaction's extreme / the zone's far edge + buf
daily ATR; take k R; the zone closed beyond its far edge first = no trade. Bot set q 0.95, check q 0.85."""
import sys, numpy as np
ARGS = sys.argv[1:]
from numba import njit
import zm_h as Z
from common import load
d = Z.d
LO, HI, DATR = d.lo.values.astype(float), d.hi.values.astype(float), d.datr_raw.values.astype(float)
@njit(cache=True)
def react(O, H, L, C, i, n_max, s, lo, hi, datr, mode, buf, tk, hold, depth):
    """mode 0: the same candle dips in and closes back out (a wick); mode 1: any close back out after a dip (may take
    several candles); depth: the dip must reach this share of the zone's width (0 = the near line)"""
    n = len(C); near = hi if s > 0 else lo; far = lo if s > 0 else hi
    lvl = near - s * depth * (hi - lo)
    dipped = False; ext = near; e = 0.0; i0 = -1
    for b in range(i, min(n - 1, i + n_max)):
        if (s > 0 and C[b] < far - 0.25 * datr) or (s < 0 and C[b] > far + 0.25 * datr):
            return np.nan, 0          # the zone broke before a reaction
        touch = (L[b] <= lvl) if s > 0 else (H[b] >= lvl)
        if touch:
            dipped = True
            ext = min(ext, L[b]) if s > 0 else max(ext, H[b])
        out = (C[b] > near) if s > 0 else (C[b] < near)
        if dipped and out and (mode == 1 or touch):
            i0 = b + 1; e = O[b + 1]; break
        if mode == 0 and dipped and not touch:
            dipped = False; ext = near
    if i0 < 0: return np.nan, 0
    stop = (min(ext, far) - buf * datr) if s > 0 else (max(ext, far) + buf * datr)
    risk = s * (e - stop)
    if risk <= e * 0.002: return np.nan, 0
    tp = e + s * tk * risk
    k = min(hold, n - i0) - 1; px = C[i0 + k]
    for q in range(min(hold, n - i0)):
        b = i0 + q
        if (s > 0 and L[b] <= stop) or (s < 0 and H[b] >= stop):
            px = O[b] if (q > 0 and ((s > 0 and O[b] <= stop) or (s < 0 and O[b] >= stop))) else stop; k = q; break
        if (s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp):
            px = tp; k = q; break
    return (s * (px - e) - (0.001 + 0.0003 * (k + 1) / 24) * e) / risk, (i0 - i) + k + 1
def labels(idx, **kw):
    R = np.full(len(d), np.nan); Hh = np.full(len(d), 24.0)
    cache = {}
    for k in idx:
        sym = Z.SYM[k]
        if sym not in cache:
            cs = load(sym); cache.clear()
            cache[sym] = ({c["time"]: n for n, c in enumerate(cs)}, np.array([c["open"] for c in cs]), np.array([c["high"] for c in cs]),
                          np.array([c["low"] for c in cs]), np.array([c["close"] for c in cs]))
        pos, O, H, L, C = cache[sym]
        i = pos.get(int(Z.T[k]))
        if i is None: continue
        r, h = react(O, H, L, C, i, 14 * 24, int(Z.SIDE[k]), LO[k], HI[k], DATR[k], kw.get("mode", 0), kw.get("buf", 0.25), kw.get("tk", 2.0), kw.get("hold", 72), kw.get("depth", 0.0))
        R[k], Hh[k] = r, max(1, h)
    return R, Hh
def replay(idx, R, H):
    o = idx[np.lexsort((-Z.SC[idx], Z.T[idx]))]
    busy, act, out = {}, [], []
    for i in o:
        if R[i] != R[i]: continue
        t = Z.T[i]; k = (Z.SYM[i], Z.SIDE[i])
        if busy.get(k, 0) > t: continue
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == Z.SIDE[i]) >= 12: continue
        end = t + int(H[i]) * 3600; busy[k] = end; act.append((end, Z.SIDE[i])); out.append((int(t), int(end), float(R[i]), int(Z.SIDE[i]), int(i)))
    return out
if __name__ == "__main__":
    srt = lambda a: a[np.argsort(Z.SYM[a], kind="stable")]
    all_idx = srt(Z.cand(0.85))
    V = [("фитиль в зону, стоп 0.25 datr, тейк 2R, 72ч", dict()), ("фитиль, тейк 3R", dict(tk=3.0)), ("фитиль, тейк 1.5R", dict(tk=1.5)),
         ("фитиль, стоп 0.5 datr, 2R", dict(buf=0.5)), ("фитиль до середины зоны, 2R", dict(depth=0.5)),
         ("закрытие обратно (до неск. свечей), 2R", dict(mode=1)), ("закрытие обратно, 3R", dict(mode=1, tk=3.0)),
         ("фитиль, 2R, держать 24ч", dict(hold=24)), ("фитиль, 3R, держать 7 дн", dict(tk=3.0, hold=168))]
    print("база (лестница бота): ")
    for q in (0.95, 0.85): Z.line(f"лестница G_1.0_R4.0 q{q}", Z.replay(Z.cand(q), "G_1.0_R4.0"), q)
    for nm, kw in V:
        R, Hh = labels(all_idx, **kw)
        for q in (0.95, 0.85):
            tr = replay(Z.cand(q), R, Hh); hrs = np.mean([(x[1] - x[0]) / 3600 for x in tr])
            Z.line(f"{nm[:30]} q{q} ~{hrs:.0f}ч", tr, q)
