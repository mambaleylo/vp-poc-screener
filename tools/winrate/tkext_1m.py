"""1m check of the take extension (tkext.py): the ⚡ 4h + 2h orders on the 40 coins with Binance 1m bars (2024-10+);
an order fills only when the price goes 0.05% through it; the stop first in a minute; the take extends when the price
touches 1 ATR and has never gone n ATR against since the fill (this minute's dip counts); the new take from the next
minute; the stop stays. The same trades at the 4h / 2h bar level side by side"""
exec(open("tkext.py").read().split("\nroll = np.arange")[0])
from common import D as ROOT
@njit
def ex1(t, o, h, l, c, i0, i1, s, lv, a, n, e, tend, tfh):
    j = -1
    for k in range(i0, i1):
        if (s > 0 and l[k] <= lv * (1 - 0.0005)) or (s < 0 and h[k] >= lv * (1 + 0.0005)):
            j = k; break
    if j < 0: return np.nan, -1
    fill = min(lv, o[j]) if s > 0 else max(lv, o[j])
    risk = 2.0 * a; sl = fill - s * risk; tp = fill + s * a; mae = 0.0; ext = False; tp2 = 0.0; k = j
    while k < len(c) and t[k] < tend:
        adv = (fill - l[k]) if s > 0 else (h[k] - fill)
        if (s > 0 and l[k] <= sl) or (s < 0 and h[k] >= sl):
            x = o[k] if (k > j and ((s > 0 and o[k] <= sl) or (s < 0 and o[k] >= sl))) else sl
            return (s * (x - fill) - (0.0007 + 0.0003 * (t[k] - t[j]) / 86400) * fill) / risk, 0
        if k > j:
            if ext:
                if (s > 0 and h[k] >= tp2) or (s < 0 and l[k] <= tp2):
                    return (s * (tp2 - fill) - (0.0004 + 0.0003 * (t[k] - t[j]) / 86400) * fill) / risk, 2
            elif (s > 0 and h[k] >= tp) or (s < 0 and l[k] <= tp):
                if n > 0 and max(mae, adv) < n * a:
                    ext = True; tp2 = fill + s * (1.0 + e) * a
                else:
                    return (s * (tp - fill) - (0.0004 + 0.0003 * (t[k] - t[j]) / 86400) * fill) / risk, 1
        if adv > mae: mae = adv
        k += 1
    k = min(k, len(c)) - 1
    return (s * (c[k] - fill) - (0.0007 + 0.0003 * (t[k] - t[j]) / 86400) * fill) / risk, 3
M1 = {}
for f in os.listdir(f"{ROOT}/data/1mz"):
    z = np.load(f"{ROOT}/data/1mz/{f}"); M1[f[:-4]] = (z["t"].astype(np.int64), z["o"], z["h"], z["l"], z["c"])
VAR = [(0, 0), (0.25, 0.5), (0.4, 1.0), (0.5, 0.5), (0.5, 1.0), (0.5, 1.5), (0.6, 1.0), (0.75, 0.75), (1.0, 1.0), (99.0, 0.5), (99.0, 1.0)]
res = {v: [] for v in VAR}; bar = {v: [] for v in VAR}; nn = 0
for v in EV:
    if v["sym"] not in M1 or v["t"] < ts(2024, 10) + 86400: continue
    t, o, h, l, c = M1[v["sym"]]; bs = v["tfh"] * 3600; w0 = v["t"] + bs
    i0 = int(np.searchsorted(t, w0)); i1 = int(np.searchsorted(t, w0 + 4 * bs))
    if i0 >= len(t) or t[i0] - w0 > 600: continue
    Tb, O, H, L, C, atr, pos = BARS[(v["sym"], v["tfh"])]
    # find the fill minute once to set the hold's end
    j = next((k for k in range(i0, i1) if ((l[k] <= v["lv"] * 0.9995) if v["s"] > 0 else (h[k] >= v["lv"] * 1.0005))), -1)
    if j < 0: continue
    tend = (t[j] // bs) * bs + 32 * bs; nn += 1
    for n_, e_ in VAR:
        r, k = ex1(t, o, h, l, c, i0, i1, v["s"], v["lv"], v["a"], n_, e_, tend, v["tfh"]); res[(n_, e_)].append((r, k))
        rb, kb, _ = ex(O, H, L, C, v["fb"], v["s"], v["fill"], v["a"], n_, e_, 0, v["tfh"]); bar[(n_, e_)].append((rb, kb))
print(f"сделок на минутках: {nn} (40 монет, с 10.2024; сигналы до отбора в пул)")
for va in VAR:
    a1 = np.array(res[va]); ab = np.array(bar[va])
    nm = "как сейчас" if va == (0, 0) else f"n={va[0]} → тейк +{va[1]} ATR"
    print(f"{nm:22s} минутки {a1[:, 0].mean():+.3f}R WR {np.isin(a1[:, 1], (1, 2)).mean()*100:.0f}% (продлено и дошло {(a1[:, 1] == 2).mean()*100:.0f}%) | "
          f"свечи {ab[:, 0].mean():+.3f}R WR {np.isin(ab[:, 1], (1, 2)).mean()*100:.0f}%", flush=True)
