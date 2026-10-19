"""Regime gates on the out-of-sample trades of a scheme (ad/<mod>_<scheme>.json): every signal is still tracked
virtually; a real trade is taken only while the gate is open. Gates use only trades CLOSED before the signal:
 - lastN: the sum of the last N closed trades > 0 (N = 10 / 20 / 40)
 - days: the sum of the trades closed in the last D days > 0 (D = 14 / 30 / 60)
 - side_lastN: the same per side (longs and shorts separately)
 - ema: an exponential average of the closed R (span N) > 0"""
import sys, json, numpy as np, datetime as dt
ARGS = sys.argv[1:]
from common import D
from mk import ts


def load(mod, scheme):
    tr = json.load(open(f"{D}/ad/{mod}_{scheme}.json"))["trades"]   # (t, end, r, coin, side)
    return sorted(tr, key=lambda x: x[0])


def gate(trades, kind, n):
    closed = sorted(trades, key=lambda x: x[1])
    ends = np.array([c[1] for c in closed]); rs = np.array([c[2] for c in closed]); sides = np.array([c[4] for c in closed])
    cs = np.concatenate([[0], np.cumsum(rs)])
    keep = []
    for t, end, r, coin, side in trades:
        k = int(np.searchsorted(ends, t, side="right"))     # closed before the signal
        if kind == "lastN":
            ok = k < n or cs[k] - cs[k - n] > 0              # too little history yet: open
        elif kind == "days":
            k0 = int(np.searchsorted(ends, t - n * 86400, side="right"))
            ok = k - k0 < 5 or cs[k] - cs[k0] > 0
        elif kind == "side_lastN":
            idx = np.where(sides[:k] == side)[0][-n:]
            ok = len(idx) < n or rs[idx].sum() > 0
        elif kind == "ema":
            a = 2 / (n + 1); e = 0.0
            for x in rs[max(0, k - 5 * n):k]:
                e = e + a * (x - e)
            ok = k < n or e > 0
        keep.append(ok)
    return [tr for tr, ok in zip(trades, keep) if ok]


def stat(trades):
    if not trades:
        return "—"
    r = np.array([t[2] for t in trades]); ends = [t[1] for t in trades]
    mon = {}
    for t in trades:
        k = dt.datetime.fromtimestamp(t[1], dt.timezone.utc).strftime("%Y-%m"); mon[k] = mon.get(k, 0) + t[2]
    yrs = []
    for Y in (2023, 2024, 2025, 2026):
        m = np.array([(ts(Y) <= e < ts(Y + 1)) for e in ends])
        yrs.append(f"{r[m].mean():+.2f}" if m.any() else "  —  ")
    allm = sorted({dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m") for t in range(ts(2023), ts(2026, 10), 86400 * 28)})
    mpos = sum(1 for k in allm if mon.get(k, 0) > 0)
    cum = np.cumsum(r); dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], cum])) - np.concatenate([[0], cum])))
    return f"n {len(r):5d} avg {r.mean():+.3f} Σ{r.sum():+6.0f} dd{dd:4.0f} мес+ {mpos}/{len(allm)} | " + " ".join(yrs)


if __name__ == "__main__":
    mod, scheme = ARGS[0], ARGS[1]
    tr = load(mod, scheme)
    print(f"{mod} {scheme} — 2023 2024 2025 2026 avg R per trade")
    print(f"{'always on':16s} {stat(tr)}")
    for kind, ns in (("lastN", (10, 20, 40)), ("days", (14, 30, 60)), ("side_lastN", (10, 20)), ("ema", (10, 30))):
        for n in ns:
            print(f"{kind + ' ' + str(n):16s} {stat(gate(tr, kind, n))}", flush=True)
