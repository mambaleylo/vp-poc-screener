"""⚡'s limits vs the weekly / monthly levels (the user's weekly-and-above study, part 2): every filled ⚡ order (_clr, both
streams) gets the distance of its limit from the last closed week's low (a long) / high (a short), the last closed month's,
and the month's open, in the order's ATR (+ = the limit on the near side of the level, i.e. the level still below a long's
limit; - = the limit beyond it, the level already broken). R by bucket, picked on 2023-2024 (the in-sample half), then the
same buckets on 2025-2026 (the check half) — a rule counts only if it holds in both. usage: ALLSUF=_clr wk_levels.py"""
import sys, os, bisect, calendar, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M
WEEK = 7 * 86400; MON = 4 * 86400
_L = {}
def levels(sym):
    """per closed week and month: the low / high; per month: the open (by the period's start time)"""
    if sym not in _L:
        fn = os.path.join(M.ST, "data", "1h", f"{sym}.csv.gz")
        if not os.path.exists(fn):
            _L[sym] = None; return None
        a = np.loadtxt(fn, delimiter=",", ndmin=2, usecols=(0, 1, 2, 3))
        t = a[:, 0].astype(np.int64); out = {}
        wk = (t - MON) // WEEK
        mo = np.array([(y - 1970) * 12 + m - 1 for y, m in (np.datetime64(int(x), "s").astype(object).timetuple()[:2] for x in t)], np.int64)
        for nm, k in (("w", wk), ("m", mo)):
            st = np.flatnonzero(np.r_[True, k[1:] != k[:-1]])
            out[nm] = (k[st], np.minimum.reduceat(a[:, 3], st), np.maximum.reduceat(a[:, 2], st), a[st, 1])
        _L[sym] = out
    return _L[sym]
def feats(o):
    L = levels(o["sym"])
    if L is None: return None
    t = o["t"]; s = o["side"]; lv = o["lv"]; a = o["atr"]
    kw = (t - MON) // WEEK; y, m = np.datetime64(int(t), "s").astype(object).timetuple()[:2]; km = (y - 1970) * 12 + m - 1
    f = {}
    for nm, k in (("w", kw), ("m", km)):
        K, LO, HI, OP = L[nm]
        i = bisect.bisect_left(K, k - 1)
        if i >= len(K) or K[i] != k - 1: return None
        lvl = LO[i] if s > 0 else HI[i]
        f[nm] = s * (lv - lvl) / a   # + : a long's limit above the last period's low (the level not broken)
        if nm == "m":
            j = bisect.bisect_left(K, k)
            f["mo"] = s * (lv - OP[j]) / a if j < len(K) and K[j] == k else None   # + : a long's limit above the month's open
    return f
BK = [(-99, -1), (-1, 0), (0, 0.5), (0.5, 1), (1, 2), (2, 99)]
def table(rows, key, lab):
    print(f"\n{lab}  (корзины: лимит минус уровень, в ATR; + = уровень ещё не пробит)")
    print("корзина | 2023-24: сделок, R | 2025-26: сделок, R")
    for lo, hi in BK:
        line = []
        for A, B in ((M.ts(2023), M.ts(2025)), (M.ts(2025), M.ts(2027))):
            r = [o["r"] for o, f in rows if f.get(key) is not None and lo <= f[key] < hi and A <= o["t"] < B]
            line.append(f"{len(r):5d}, {np.mean(r) if r else 0:+.3f}")
        print(f"[{lo:g}, {hi:g}) | " + " | ".join(line))
if __name__ == "__main__":
    OR = [o for o in MA2.orders() if o["filled"] and o["t"] >= M.ts(2023)]
    rows = [(o, f) for o in OR for f in [feats(o)] if f]
    print(f"исполненных ⚡ 2023-2026: {len(OR)}, с уровнями {len(rows)}; R всех: 2023-24 {np.mean([o['r'] for o, _ in rows if o['t'] < M.ts(2025)]):+.3f}, "
          f"2025-26 {np.mean([o['r'] for o, _ in rows if o['t'] >= M.ts(2025)]):+.3f}")
    table(rows, "w", "минимум (лонг) / максимум (шорт) прошлой недели")
    table(rows, "m", "минимум / максимум прошлого месяца")
    table(rows, "mo", "открытие текущего месяца")
    for st in ("wick4h", "close2h"):
        sub = [(o, f) for o, f in rows if o["stream"] == st]
        table(sub, "w", f"[{st}] прошлая неделя")
    print("levels done", flush=True)
