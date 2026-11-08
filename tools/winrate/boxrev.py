"""Hypothesis 10 (the user's screenshots, ACEUSDT 4h): after a big move the price stalls in a few similar small candles, then it
turns back. On 4h candles (built from the lab-store 1h, the 210 Классика / ⚡ coins): the impulse — the close moved >= I x ATR(14)
(the ATR before the impulse) over the M bars before the stall; the stall — K bars right after it, each bar's range <= 1.2 ATR, the
largest range <= 3 x the smallest (similar candles), the whole box (max high - min low) <= B x ATR. The trade, against the impulse
(rev) or with it (cont, the control): "next" — at the open after the stall; "brk" — the first of the next 3 bars that closes beyond
the box's far side, in at the next open. The stop 0.2 ATR beyond the box's other side; the take T x the stop; out after H bars;
the fee 0.1% + the funding. One per coin & side for its hold. Each config: n / mean R / WR in 2023–24 and 2025–26; the configs
ranked by 2023–24 only, the top ones shown with 2025–26 (never used). The baseline "K0": the same impulse, no stall needed
(in at the next bar's open, the stop 1 ATR beyond the last bar's extreme) — does the stall add anything over plain mean reversion?
-> <LABSTORE>/wf/boxrev.json"""
import os, json, gzip, itertools, calendar, numpy as np
from numba import njit
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
sp = json.load(open("lv/split.json")); COINS = sorted(set(sp["bot"]) | set(sp["chk"]))
ts = lambda y, m=1: calendar.timegm((y, m, 1, 0, 0, 0)); A0, MID, END = ts(2023), ts(2025), ts(2026, 10)
B4 = 4 * 3600
def load4(sym):
    a = np.loadtxt(f"{ST}/data/1h/{sym}.csv.gz", delimiter=",", ndmin=2); t = a[:, 0].astype(np.int64); k = np.concatenate([[True], np.diff(t) > 0]); a = a[k]
    t = a[:, 0].astype(np.int64); g = t // B4; u, st = np.unique(g, return_index=True); en = np.append(st[1:], len(t))
    full = (en - st) == 4   # only complete 4h bars (a gap in the hours -> the bar dropped)
    T = u[full] * B4; O = a[st[full], 1]; C = a[en[full] - 1, 4]
    H = np.maximum.reduceat(a[:, 2], st)[full]; L = np.minimum.reduceat(a[:, 3], st)[full]
    pc = np.concatenate([[C[0]], C[:-1]]); tr = np.maximum(H - L, np.maximum(np.abs(H - pc), np.abs(L - pc)))
    atr = np.empty(len(C)); a_ = tr[0]
    for i in range(len(C)): a_ = tr[i] if i == 0 else (a_ * 13 + tr[i]) / 14; atr[i] = a_
    return T, O, H, L, C, atr
@njit(cache=True)
def walk(O, H, L, C, i, s, stop, take, hold):   # in at O[i]
    e = O[i]; risk = abs(e - stop)
    if risk <= 0 or (s > 0 and e <= stop) or (s < 0 and e >= stop): return np.nan, 0
    tp = e + s * take * risk; n = min(len(C) - 1, i + hold - 1)
    for b in range(i, n + 1):
        f = e * 0.001 + e * 0.0003 * (b - i + 1) * 4 / 24
        if (s > 0 and L[b] <= stop) or (s < 0 and H[b] >= stop):
            ex = O[b] if ((s > 0 and O[b] <= stop) or (s < 0 and O[b] >= stop)) else stop
            return (s * (ex - e) - f) / risk, b - i + 1
        if (s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp):
            ex = O[b] if ((s > 0 and O[b] >= tp) or (s < 0 and O[b] <= tp)) else tp
            return (s * (ex - e) - f) / risk, b - i + 1
    f = e * 0.001 + e * 0.0003 * (n - i + 1) * 4 / 24
    return (s * (C[n] - e) - f) / risk, n - i + 1
GRID = dict(M=(3, 6), I=(3.0, 5.0), K=(0, 3, 4, 5), B=(1.0, 1.5, 2.5), E=("next", "brk"), D=("rev", "cont"), T=(1.5, 2.5, 4.0), H=(6, 12, 24))
DATA = {}
for sym in COINS:
    try: DATA[sym] = load4(sym)
    except Exception: continue
print("монет:", len(DATA), flush=True)
EV = {}   # (M, I, K, B) -> [(t, sym, d, i_end, lo, hi, atr)]  d: the impulse's direction, i_end: the stall's last bar
for sym, (T, O, H, L, C, atr) in DATA.items():
    n = len(C); rr = (H - L)
    for M, I, K in itertools.product(GRID["M"], GRID["I"], GRID["K"]):
        for e in np.where((T >= A0) & (T < END))[0]:
            j = e - K + 1; p = j - 1 - M   # the stall j..e, the impulse p..j-1
            if p < 15 or e + 5 >= n: continue
            a = atr[p]
            if a <= 0: continue
            mv = (C[j - 1] - C[p]) / a
            if abs(mv) < I: continue
            d = 1 if mv > 0 else -1
            if K == 0:
                lo, hi = L[e], H[e]
                for B in GRID["B"]:
                    EV.setdefault((M, I, K, B), []).append((int(T[e]), sym, d, e, lo, hi, a))
                continue
            r = rr[j:e + 1]
            if r.max() > 1.2 * a or r.max() > 3 * max(r.min(), 1e-12): continue
            # the stall must not itself continue the impulse much: its box overlaps the impulse's last bar
            lo, hi = L[j:e + 1].min(), H[j:e + 1].max()
            if d > 0 and lo > H[j - 1]: continue
            if d < 0 and hi < L[j - 1]: continue
            for B in GRID["B"]:
                if hi - lo <= B * a: EV.setdefault((M, I, K, B), []).append((int(T[e]), sym, d, e, lo, hi, a))
for k in EV: EV[k].sort()
print("событий по наборам (M, I, K, B):", {f"{k}": len(v) for k, v in sorted(EV.items()) if k[3] == 1.5}, flush=True)
res = []
for M, I, K, B, E, D, Tk, Hh in itertools.product(*GRID.values()):
    if K == 0 and (B != 1.0 or E != "next"): continue
    busy = {}; ra, rb = [], []
    for t, sym, d, e, lo, hi, a in EV.get((M, I, K, B), ()):
        s = -d if D == "rev" else d
        if busy.get((sym, s), 0) > t: continue
        T, O, H, L, C, atr = DATA[sym]
        if E == "next": i = e + 1
        else:
            i = -1
            for b in range(e + 1, e + 4):
                if (s < 0 and C[b] < lo) or (s > 0 and C[b] > hi): i = b + 1; break
            if i < 0 or i >= len(C): continue
        if K == 0: stop = (H[e] + a) if s < 0 else (L[e] - a)
        else: stop = (hi + 0.2 * a) if s < 0 else (lo - 0.2 * a)
        r, k = walk(O, H, L, C, i, s, stop, Tk, Hh)
        if r != r: continue
        busy[(sym, s)] = int(T[i - 1]) + (k + 1) * B4
        (ra if t < MID else rb).append(r)
    if len(ra) >= 40 and len(rb) >= 40:
        res.append({"M": M, "I": I, "K": K, "B": B, "E": E, "D": D, "T": Tk, "H": Hh,
                    "a": [len(ra), round(float(np.mean(ra)), 3), round(float(np.mean(np.array(ra) > 0) * 100), 1)],
                    "b": [len(rb), round(float(np.mean(rb)), 3), round(float(np.mean(np.array(rb) > 0) * 100), 1)]})
res.sort(key=lambda x: -x["a"][1])
for D in ("rev", "cont"):
    for kk in ("K0", "K3-5"):
        rs = [x for x in res if x["D"] == D and ((x["K"] == 0) == (kk == "K0"))]
        if not rs: continue
        print(f"\n=== {'ПРОТИВ импульса (идея)' if D == 'rev' else 'ПО импульсу (контроль)'}, {'без остановки (база)' if kk == 'K0' else 'с остановкой 3–5 свечей'}: "
              f"конфигураций {len(rs)} | плюс в 2023–24: {sum(x['a'][1] > 0 for x in rs)} | плюс в обоих: {sum(x['a'][1] > 0 and x['b'][1] > 0 for x in rs)}", flush=True)
        print("топ-10 по 2023–24 (M баров импульса, I ATR, K свечей, коробка B ATR, вход, тейк, баров) | 2023–24: n, R, WR | 2025–26: n, R, WR", flush=True)
        for x in rs[:10]: print(f"M{x['M']} I{x['I']} K{x['K']} B{x['B']} {x['E']} T{x['T']} H{x['H']} | {x['a']} | {x['b']}", flush=True)
        if len(rs) > 2: print(f"связь R 2023–24 и 2025–26: {np.corrcoef([x['a'][1] for x in rs], [x['b'][1] for x in rs])[0, 1]:.2f}; "
                              f"медиана R 2023–24 {np.median([x['a'][1] for x in rs]):+.3f}, 2025–26 {np.median([x['b'][1] for x in rs]):+.3f}", flush=True)
json.dump(res, open(f"{ST}/wf/boxrev.json", "w"))
print("boxrev done", flush=True)
