"""Hypothesis 11 (the user: "по порядку все"): short the new futures listings. A coin is a listing when its first lab-store 1h
candle is in 2023-01 .. 2026-06 (the archive starts 2021-01, so these are real first days). After D days from the listing:
the regime filter (any / up: the price above the first day's close / down: below it), then a short at the next hour's open;
the stop S % above the entry, the take T x the stop (0: none), out after H days. The fee 0.1% + 0.1% extra slippage (thin
books) + the coin's real funding (a short gets a positive rate, pays a negative one). One trade per coin.
The control: for every listing event the same rule at the same hour on a random mature coin (listed > 1 year before, with
funding) — is it "new listing" or just "alts fell in those months"?  Each config: n / mean R / WR 2023–24 and 2025–26;
ranked by 2023–24 only; the per-year R; the control's R. -> <LABSTORE>/wf/listing.json"""
import os, json, gzip, time, itertools, calendar, numpy as np
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store"); D1 = f"{ST}/data/1h"; DF = f"{ST}/data/funding"
ts = lambda y, m=1: calendar.timegm((y, m, 1, 0, 0, 0)); A0, MID, LAST = ts(2023), ts(2025), ts(2026, 7)
HR = 3600; DAY = 86400
def load(sym):
    a = np.loadtxt(f"{D1}/{sym}.csv.gz", delimiter=",", ndmin=2); t = a[:, 0].astype(np.int64); k = np.concatenate([[True], np.diff(t) > 0]); a = a[k]
    f = np.zeros((0, 2))
    if os.path.exists(f"{DF}/{sym}.csv") and os.path.getsize(f"{DF}/{sym}.csv") > 0: f = np.loadtxt(f"{DF}/{sym}.csv", delimiter=",", ndmin=2)
    return a[:, 0].astype(np.int64), a[:, 1], a[:, 2], a[:, 3], a[:, 4], f
FIRST = {}
for fn in os.listdir(D1):
    with gzip.open(f"{D1}/{fn}", "rt") as h: FIRST[fn[:-7]] = int(h.readline().split(",")[0])
NEW = sorted(s for s, t in FIRST.items() if A0 <= t < LAST)
MAT = sorted(s for s, t in FIRST.items() if t < A0 - 365 * DAY and os.path.exists(f"{DF}/{s}.csv"))
nf = sum(not os.path.exists(f"{DF}/{s}.csv") or os.path.getsize(f"{DF}/{s}.csv") == 0 for s in NEW)
print(f"листингов 2023-01..2026-06: {len(NEW)} (без фандинга: {nf} — для них фандинг 0) | зрелых монет для контроля: {len(MAT)}", flush=True)
DATA = {}
for s in set(NEW) | set(MAT):
    try: DATA[s] = load(s)
    except Exception: pass
def trade(sym, t_in, S, T, H, s=-1):
    """the short (s=-1) from the open of the hour t_in: R, or None"""
    tt, O, Hh, L, C, f = DATA[sym]
    i = np.searchsorted(tt, t_in)
    if i >= len(tt) or tt[i] - t_in > 6 * HR: return None
    e = O[i]; stop = e * (1 + S / 100) if s < 0 else e * (1 - S / 100); risk = abs(stop - e); tp = e + s * T * risk if T else None
    n = np.searchsorted(tt, t_in + H * DAY) - 1; n = min(n, len(tt) - 1)
    if n <= i: return None
    ex = None; b_out = n
    for b in range(i, n + 1):
        if (s < 0 and Hh[b] >= stop) or (s > 0 and L[b] <= stop):
            ex = O[b] if ((s < 0 and O[b] >= stop) or (s > 0 and O[b] <= stop)) else stop; b_out = b; break
        if tp is not None and ((s < 0 and L[b] <= tp) or (s > 0 and Hh[b] >= tp)):
            ex = O[b] if ((s < 0 and O[b] <= tp) or (s > 0 and O[b] >= tp)) else tp; b_out = b; break
    if ex is None: ex = C[n]
    t_out = tt[b_out] + HR
    fund = 0.0
    if len(f): m = (f[:, 0] >= tt[i]) & (f[:, 0] < t_out); fund = float(f[m, 1].sum())   # the rate x the notional; a short gets +rate
    pnl = s * (ex - e) - e * 0.002 + (-s) * fund * e
    return pnl / risk
GRID = dict(D=(1, 2, 3, 5, 7, 14, 30), G=("any", "up", "down"), S=(15, 25, 40), T=(0, 1.5, 3.0), H=(7, 14, 30))
rng = np.random.default_rng(11)
CTRL = {}
for s in NEW:
    if s not in DATA: continue
    t0 = DATA[s][0][0]
    cand = [m for m in MAT if m in DATA and DATA[m][0][0] < t0 - 365 * DAY]
    CTRL[s] = cand[rng.integers(len(cand))] if cand else None
res = []
for D, G, S, T, H in itertools.product(*GRID.values()):
    ra, rb, rc, yy = [], [], [], {}
    for s in NEW:
        if s not in DATA: continue
        tt, O, Hh, L, C, f = DATA[s]; t0 = tt[0]
        tin = (t0 // HR) * HR + D * DAY
        if tin + H * DAY > tt[-1] + HR: continue
        first = C[min(23, len(C) - 1)]; j = np.searchsorted(tt, tin) - 1
        if j < 0: continue
        if G == "up" and not C[j] > first: continue
        if G == "down" and not C[j] < first: continue
        r = trade(s, tin, S, T, H)
        if r is None: continue
        (ra if tin < MID else rb).append(r); yy.setdefault(time.gmtime(tin).tm_year, []).append(r)
        if CTRL.get(s):
            rcx = trade(CTRL[s], tin, S, T, H)
            if rcx is not None: rc.append(rcx)
    if len(ra) >= 30 and len(rb) >= 30:
        al = np.array(ra + rb)
        res.append({"D": D, "G": G, "S": S, "T": T, "H": H,
                    "a": [len(ra), round(float(np.mean(ra)), 3), round(float(np.mean(np.array(ra) > 0) * 100), 1)],
                    "b": [len(rb), round(float(np.mean(rb)), 3), round(float(np.mean(np.array(rb) > 0) * 100), 1)],
                    "all": [len(al), round(float(al.mean()), 3), round(float(al.mean() / (al.std() / np.sqrt(len(al)))), 2)],
                    "c": [len(rc), round(float(np.mean(rc)), 3) if rc else None],
                    "Y": {y: [len(v), round(float(np.mean(v)), 2)] for y, v in sorted(yy.items())}})
res.sort(key=lambda x: -x["a"][1])
print(f"конфигураций: {len(res)} | плюс в 2023–24: {sum(x['a'][1] > 0 for x in res)} | плюс в обоих: {sum(x['a'][1] > 0 and x['b'][1] > 0 for x in res)} | "
      f"плюс в обоих и лучше контроля: {sum(x['a'][1] > 0 and x['b'][1] > 0 and x['c'][1] is not None and x['all'][1] > x['c'][1] for x in res)}", flush=True)
print("топ-25 по 2023–24 (D дней после листинга, режим, стоп %, тейк R, дней) | 2023–24 n,R,WR | 2025–26 n,R,WR | всё n,R,t | контроль n,R | по годам", flush=True)
for x in res[:25]: print(f"D{x['D']} {x['G']} S{x['S']} T{x['T']} H{x['H']} | {x['a']} | {x['b']} | {x['all']} | {x['c']} | {x['Y']}", flush=True)
for key in ("D", "G", "S", "T", "H"):
    print(f"по {key}: " + "; ".join(f"{v}: {np.median([x['a'][1] for x in res if x[key] == v]):+.3f} / {np.median([x['b'][1] for x in res if x[key] == v]):+.3f} / контроль {np.median([x['c'][1] for x in res if x[key] == v and x['c'][1] is not None]):+.3f}"
                                    for v in GRID[key] if any(x[key] == v for x in res)), flush=True)
cor = np.corrcoef([x["a"][1] for x in res], [x["b"][1] for x in res])[0, 1] if len(res) > 2 else float("nan")
print(f"связь R 2023–24 и 2025–26 по конфигурациям: {cor:.2f}", flush=True)
json.dump(res, open(f"{ST}/wf/listing.json", "w"))
print("listing done", flush=True)
