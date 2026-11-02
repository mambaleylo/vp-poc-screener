"""A weekly module of its own (the user's weekly-and-above study, part 3): fixed rules on weekly bars (Monday 00:00 UTC) built
from the daily SPOT candles since 2017 (dl_spot1d.py — the long history: 2018's and 2022's bear markets), the 127 research
coins, nothing fitted:
  W1 breakout   the week closes above the 20 weeks' high and above its EMA20 (a long; a short mirrored) -> the next week's open
  W2 pullback   EMA20 above EMA50, the week's low touches EMA20 and it closes above (a long; a short mirrored)
The exit for both: the stop 2 x ATR14 (weekly) from the entry, hit by a week's low / high (at the stop; a gap at the open);
else out at the close of the first week closing beyond the 10 weeks' opposite extreme (a trailing channel), at most 52 weeks.
R per the stop's distance less the costs: 0.1% a round trip + the funding 0.03% a day held (a perpetual's). One trade a coin
& side at a time. By year (the entry's), WR, R, the sum, the longest R drawdown; BTC alone; the long / short split.
Caveat: the 127 coins are today's survivors — a long trend rule looks better on them than it would have live.
usage: wk_module.py DIR"""
import sys, os, glob, numpy as np
D = sys.argv[1] if len(sys.argv) > 1 else "/home/user/wk_data/spot1d"
WEEK = 7 * 86400; MON = 4 * 86400
def ema(x, n):
    e = np.empty(len(x)); e[0] = x[0]
    for i in range(1, len(x)): e[i] = e[i - 1] + 2 / (n + 1) * (x[i] - e[i - 1])
    return e
def weeks(fn):
    a = np.loadtxt(fn, delimiter=",", ndmin=2)
    if len(a) < 400: return None
    t = a[:, 0].astype(np.int64); wk = (t - MON) // WEEK
    st = np.flatnonzero(np.r_[True, wk[1:] != wk[:-1]]); en = np.r_[st[1:], len(t)]
    full = (en - st) == 7; st, en = st[full], en[full]   # complete weeks only
    T = (wk[st] * WEEK + MON); O = a[st, 1]; H = np.array([a[s:e, 2].max() for s, e in zip(st, en)])
    L = np.array([a[s:e, 3].min() for s, e in zip(st, en)]); C = a[en - 1, 4]
    return T, O, H, L, C
def atr(H, L, C, n=14):
    tr = np.maximum(H - L, np.maximum(abs(H - np.r_[C[0], C[:-1]]), abs(L - np.r_[C[0], C[:-1]])))
    out = np.empty(len(tr)); out[0] = tr[0]
    for i in range(1, len(tr)): out[i] = out[i - 1] + (tr[i] - out[i - 1]) / n
    return out
def trades(T, O, H, L, C, rule):
    E20, E50, A = ema(C, 20), ema(C, 50), atr(H, L, C); out = []; busy = {1: -1, -1: -1}
    for i in range(50, len(C) - 1):
        for s in (1, -1):
            if i <= busy[s]: continue
            if rule == "W1":
                hi20 = H[i - 20:i].max(); lo20 = L[i - 20:i].min()
                sig = (C[i] > hi20 and C[i] > E20[i]) if s > 0 else (C[i] < lo20 and C[i] < E20[i])
            else:
                sig = (E20[i] > E50[i] and L[i] <= E20[i] < C[i]) if s > 0 else (E20[i] < E50[i] and H[i] >= E20[i] > C[i])
            if not sig: continue
            j = i + 1; e = O[j]; sd = 2 * A[i]; stp = e - s * sd; x = None; k = j
            while k < len(C) and k <= j + 52:
                if s > 0 and L[k] <= stp: x = min(stp, O[k]) if k > j else stp; break
                if s < 0 and H[k] >= stp: x = max(stp, O[k]) if k > j else stp; break
                if k - 10 >= j - 9:
                    ch = L[k - 10:k].min() if s > 0 else H[k - 10:k].max()
                    if (s > 0 and C[k] < ch) or (s < 0 and C[k] > ch): x = C[k]; break
                k += 1
            if x is None:
                if k >= len(C): continue   # still open at the data's end
                x = C[min(k, len(C) - 1)]
            days = (min(k, len(C) - 1) - j + 1) * 7
            r = (s * (x - e) / e - 0.001 - 0.0003 * days) / (sd / e)
            out.append((int(T[j]), s, float(r), days)); busy[s] = k
    return out
def stats(rows, lab):
    if not rows: print(f"{lab}: нет сделок"); return
    r = np.array([x[2] for x in sorted(rows)]); c = np.cumsum(r); dd = float(np.max(np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c]))
    print(f"{lab}: {len(r)} сделок, WR {(r > 0).mean() * 100:.0f}%, {r.mean():+.3f}R, Σ{r.sum():+.0f}R, просадка {dd:.0f}R, "
          f"в сделке ~{np.mean([x[3] for x in rows]):.0f} дн", flush=True)
if __name__ == "__main__":
    W = {os.path.basename(f)[:-4]: w for f in sorted(glob.glob(f"{D}/*.csv")) for w in [weeks(f)] if w}
    print(f"монет с историей: {len(W)}, BTC с {np.datetime64(int(W['BTCUSDT'][0][0]), 's')}", flush=True)
    for rule in ("W1", "W2"):
        print(f"\n=== {rule} {'пробой 20 недель по EMA20' if rule == 'W1' else 'откат к недельной EMA20 в тренде'}", flush=True)
        allr = {sym: trades(*w, rule) for sym, w in W.items()}
        rows = [x for v in allr.values() for x in v]
        stats(rows, "все")
        for s, nm in ((1, "лонги"), (-1, "шорты")): stats([x for x in rows if x[1] == s], nm)
        stats(allr.get("BTCUSDT", []), "только BTC")
        for Y in range(2018, 2027):
            a, b = np.datetime64(f"{Y}-01-01").astype("datetime64[s]").astype(int), np.datetime64(f"{Y + 1}-01-01").astype("datetime64[s]").astype(int)
            yr = [x for x in rows if a <= x[0] < b]
            stats(yr, f"  {Y}")
    print("wk module done", flush=True)
