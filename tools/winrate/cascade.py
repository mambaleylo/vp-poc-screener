"""Hypothesis 8 (the user picked it): the rebound after a liquidation cascade. The event at a 1h close (the 210 Классика / ⚡ coins,
lab-store 1h candles + metrics' hourly open interest): a flush down — the bar's low at least D x ATR(14) below its open, the close
back up by at least W of the range (a long lower wick), the open interest of the hour down by at least O %, the volume >= V x its
24 h median; the mirror for a squeeze up (a short). Entry: the next hour's open; the stop 0.2 ATR beyond the wick's extreme; the take
T x the stop; out after H hours; the fee 0.1% + the funding. One per coin & side for its hold. The grid of (D, W, O, V, T, H): each
config's n / mean R / WR in 2023–24 and 2025–26; the configs ranked by 2023–24 only, the top ones shown with 2025–26 (never used).
-> <LABSTORE>/wf/cascade.json"""
import os, json, gzip, itertools, calendar, numpy as np
from numba import njit
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
sp = json.load(open("lv/split.json")); COINS = sorted(set(sp["bot"]) | set(sp["chk"]))
ts = lambda y, m=1: calendar.timegm((y, m, 1, 0, 0, 0)); A0, MID, END = ts(2023), ts(2025), ts(2026, 10)
def load(sym):
    a = np.loadtxt(f"{ST}/data/1h/{sym}.csv.gz", delimiter=",", ndmin=2); t = a[:, 0].astype(np.int64); k = np.concatenate([[True], np.diff(t) > 0]); a = a[k]
    T, O, H, L, C, V = a[:, 0].astype(np.int64), a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5]
    oi = np.full(len(T), np.nan); fn = f"{ST}/data/metrics/{sym}.csv"
    if os.path.exists(fn):
        m = np.genfromtxt(fn, delimiter=",", names=True)
        if m.size > 10:
            mt = m["t"].astype(np.int64); j = np.searchsorted(mt, T); ok = (j < len(mt)) & (mt[np.minimum(j, len(mt) - 1)] == T); oi[ok] = m["oi"][j[ok]]
    pc = np.concatenate([[C[0]], C[:-1]]); tr = np.maximum(H - L, np.maximum(np.abs(H - pc), np.abs(L - pc)))
    atr = np.empty(len(C)); a_ = tr[0]
    for i in range(len(C)): a_ = tr[i] if i == 0 else (a_ * 13 + tr[i]) / 14; atr[i] = a_
    return T, O, H, L, C, V, oi, atr
@njit(cache=True)
def walk(O, H, L, C, i, s, stop, take, hold):
    e = O[i + 1]; risk = abs(e - stop)
    if risk <= 0: return np.nan, 0
    tp = e + s * take * risk; n = min(len(C) - 1, i + hold)
    for b in range(i + 1, n + 1):
        if (s > 0 and L[b] <= stop) or (s < 0 and H[b] >= stop):
            ex = O[b] if ((s > 0 and O[b] <= stop) or (s < 0 and O[b] >= stop)) and b > i + 1 else stop
            return (s * (ex - e) - e * 0.001 - e * 0.0003 * (b - i) / 24) / risk, b - i
        if b > i + 1 and ((s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp)):
            return (take * risk - e * 0.001 - e * 0.0003 * (b - i) / 24) / risk, b - i
    return (s * (C[n] - e) - e * 0.001 - e * 0.0003 * (n - i) / 24) / risk, n - i
GRID = dict(D=(2.0, 3.0, 4.0), W=(0.3, 0.5), O=(0.0, 2.0, 4.0), V=(2.0, 4.0), T=(1.5, 2.5, 4.0), H=(12, 24, 48))
SIDES = [int(x) for x in os.environ.get("CASC_SIDES", "1,-1").split(",")]   # 1: the longs after a flush only, -1: the shorts after a squeeze
EV = []   # (t, coin, side, D, W, Opct, Vx, i)
DATA = {}
for sym in COINS:
    try: T, O, H, L, C, V, oi, atr = load(sym)
    except Exception: continue
    DATA[sym] = (T, O, H, L, C, V, oi, atr)
    medv = np.full(len(V), np.nan); medv[24:] = np.median(np.lib.stride_tricks.sliding_window_view(V, 24)[:-1], axis=1)   # the median of the 24 hours before
    doi = np.full(len(T), np.nan); doi[1:] = (oi[1:] / oi[:-1] - 1) * 100
    rng = np.maximum(H - L, 1e-12); patr = np.concatenate([[np.nan], atr[:-1]])
    for i in np.where((T >= A0) & (T < END))[0]:
        if i + 2 >= len(T) or not np.isfinite(patr[i]) or patr[i] <= 0 or not np.isfinite(medv[i]) or medv[i] <= 0: continue
        dn, up = (O[i] - L[i]) / patr[i], (H[i] - O[i]) / patr[i]
        if dn >= 2.0 and (C[i] - L[i]) / rng[i] >= 0.3: EV.append((int(T[i]), sym, 1, dn, (C[i] - L[i]) / rng[i], -doi[i], V[i] / medv[i], i))
        if up >= 2.0 and (H[i] - C[i]) / rng[i] >= 0.3: EV.append((int(T[i]), sym, -1, up, (H[i] - C[i]) / rng[i], -doi[i], V[i] / medv[i], i))
print("событий-кандидатов:", len(EV), "монет:", len(DATA), flush=True)
EV.sort()
res = []
for D, W, Op, Vx, Tk, Hh in itertools.product(*GRID.values()):
    busy = {}; ra, rb = [], []
    for t, sym, s, dd, ww, oo, vv, i in EV:
        if s not in SIDES or dd < D or ww < W or vv < Vx or not (oo >= Op if Op > 0 else True): continue
        if busy.get((sym, s), 0) > t: continue
        T, O, H, L, C, V, oi, atr = DATA[sym]; a = atr[i - 1]
        stop = (L[i] - 0.2 * a) if s > 0 else (H[i] + 0.2 * a)
        r, k = walk(O, H, L, C, i, s, stop, Tk, Hh)
        if r != r: continue
        busy[(sym, s)] = t + (k + 1) * 3600
        (ra if t < MID else rb).append(r)
    if len(ra) >= 40 and len(rb) >= 40:
        res.append({"D": D, "W": W, "O": Op, "V": Vx, "T": Tk, "H": Hh, "a": [len(ra), round(float(np.mean(ra)), 3), round(float(np.mean(np.array(ra) > 0) * 100), 1)],
                    "b": [len(rb), round(float(np.mean(rb)), 3), round(float(np.mean(np.array(rb) > 0) * 100), 1)]})
res.sort(key=lambda x: -x["a"][1])
print("конфигураций:", len(res), "| положительных в 2023–24:", sum(x["a"][1] > 0 for x in res), "| в обоих периодах:", sum(x["a"][1] > 0 and x["b"][1] > 0 for x in res), flush=True)
print("топ-15 по 2023–24 (D ATR, тень W, падение OI %, объём ×, тейк, часы) | 2023–24: n, R, WR | 2025–26: n, R, WR", flush=True)
for x in res[:15]: print(f"D{x['D']} W{x['W']} OI-{x['O']}% V{x['V']}x T{x['T']} H{x['H']} | {x['a']} | {x['b']}", flush=True)
cor = np.corrcoef([x["a"][1] for x in res], [x["b"][1] for x in res])[0, 1] if len(res) > 2 else float("nan")
print(f"связь R 2023–24 и 2025–26 по конфигурациям: {cor:.2f}", flush=True)
json.dump(res, open(f"{ST}/wf/cascade" + os.environ.get("CASC_SIDES", "").replace(",", "_").replace("-", "m") + ".json", "w"))
print("cascade done", flush=True)
