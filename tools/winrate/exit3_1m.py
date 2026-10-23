"""1m check of the stop's size with the v0.99.690 take (40 coins, 2024-10+, the fill 0.05% through, the stop first in a minute)"""
exec(open("tkext.py").read().split("\nroll = np.arange")[0])
from common import D as ROOT
@njit
def ex1(t, o, h, l, c, i0, i1, s, lv, a, n, stp, tkn, tend):
    j = -1
    for k in range(i0, i1):
        if (s > 0 and l[k] <= lv * (1 - 0.0005)) or (s < 0 and h[k] >= lv * (1 + 0.0005)):
            j = k; break
    if j < 0: return np.nan, -1
    fill = min(lv, o[j]) if s > 0 else max(lv, o[j])
    risk = stp * a; sl = fill - s * risk; tp1 = fill + s * a; tpn = fill + s * tkn * a; tp2 = fill + s * 2.0 * a
    mae = 0.0; ext = False; pulled = False; k = j
    while k < len(c) and t[k] < tend:
        adv = (fill - l[k]) if s > 0 else (h[k] - fill)
        if (s > 0 and l[k] <= sl) or (s < 0 and h[k] >= sl):
            x = o[k] if (k > j and ((s > 0 and o[k] <= sl) or (s < 0 and o[k] >= sl))) else sl
            return (s * (x - fill) - (0.0007 + 0.0003 * (t[k] - t[j]) / 86400) * fill) / risk, 0
        if k > j:
            if ext:
                if (s > 0 and h[k] >= tp2) or (s < 0 and l[k] <= tp2):
                    return (s * (tp2 - fill) - (0.0004 + 0.0003 * (t[k] - t[j]) / 86400) * fill) / risk, 2
            elif pulled:
                if (s > 0 and h[k] >= tpn) or (s < 0 and l[k] <= tpn):
                    return (s * (tpn - fill) - (0.0004 + 0.0003 * (t[k] - t[j]) / 86400) * fill) / risk, 1
            elif (s > 0 and h[k] >= tp1) or (s < 0 and l[k] <= tp1):
                if max(mae, adv) < n * a:
                    ext = True
                else:
                    x = tp1 if tkn >= 1.0 else tpn
                    return (s * (x - fill) - (0.0004 + 0.0003 * (t[k] - t[j]) / 86400) * fill) / risk, 1
        if adv > mae: mae = adv
        if not ext and mae >= n * a: pulled = True
        k += 1
    k = min(k, len(c)) - 1
    return (s * (c[k] - fill) - (0.0007 + 0.0003 * (t[k] - t[j]) / 86400) * fill) / risk, 3
M1 = {}
for f in os.listdir(f"{ROOT}/data/1mz"):
    z = np.load(f"{ROOT}/data/1mz/{f}"); M1[f[:-4]] = (z["t"].astype(np.int64), z["o"], z["h"], z["l"], z["c"])
VAR = [(0.4, 2.0, 1.0), (0.4, 1.75, 1.0), (0.4, 1.5, 1.0), (0.3, 1.5, 1.0), (0.5, 1.5, 1.0), (0.4, 1.25, 1.0), (0.4, 1.0, 1.0), (0.4, 1.5, 0.75), (0.4, 2.0, 0.75)]
res = {v: [] for v in VAR}; bar = {v: [] for v in VAR}; nn = 0
exec(open("exit2.py").read().split("@njit\ndef ex2")[1].join(["@njit\ndef ex2", ""]).split("\ndef run2")[0])
for v in EV:
    if v["sym"] not in M1 or v["t"] < ts(2024, 10) + 86400: continue
    t, o, h, l, c = M1[v["sym"]]; bs = v["tfh"] * 3600; w0 = v["t"] + bs
    i0 = int(np.searchsorted(t, w0)); i1 = int(np.searchsorted(t, w0 + 4 * bs))
    if i0 >= len(t) or t[i0] - w0 > 600: continue
    j = next((k for k in range(i0, i1) if ((l[k] <= v["lv"] * 0.9995) if v["s"] > 0 else (h[k] >= v["lv"] * 1.0005))), -1)
    if j < 0: continue
    tend = (t[j] // bs) * bs + 32 * bs; nn += 1
    Tb, O, H, L, C, atr, pos = BARS[(v["sym"], v["tfh"])]
    for n_, stp, tkn in VAR:
        r, k = ex1(t, o, h, l, c, i0, i1, v["s"], v["lv"], v["a"], n_, stp, tkn, tend); res[(n_, stp, tkn)].append((r, k))
        rb, kb, _ = ex2(O, H, L, C, v["fb"], v["s"], v["fill"], v["a"], n_, tkn, 2.0, stp, 99.0, 32, 32, 32, v["tfh"]); bar[(n_, stp, tkn)].append((rb, kb))
print(f"сделок на минутках: {nn}")
for va in VAR:
    a1 = np.array(res[va]); ab = np.array(bar[va])
    print(f"откат {va[0]}, стоп {va[1]}, после отката {va[2]}: минутки {a1[:, 0].mean():+.3f}R WR {np.isin(a1[:, 1], (1, 2)).mean()*100:.0f}% | свечи {ab[:, 0].mean():+.3f}R WR {np.isin(ab[:, 1], (1, 2)).mean()*100:.0f}%", flush=True)
