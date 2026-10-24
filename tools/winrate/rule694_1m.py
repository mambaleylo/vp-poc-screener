"""v0.99.694 candidate: the stop on the close of the chart's candle (4h / 2h) or 4h for all, vs the 1h close (692). 1m check of the exits (40 coins with Binance 1m bars, 2024-10 on): the fill 0.05% through the limit; then minute
by minute: the emergency stop (3 ATR) first in a minute, the take (1.1 ATR) from the next minute, at each hour's close
(the last minute's close of a UTC hour) out if beyond the 2 ATR stop; vs the take 1 / stop 2 by a touch and the take
2/1 (v0.99.690); out after 32 bars of the chart. R per the 2 ATR"""
exec(open("tkext.py").read().split("\nroll = np.arange")[0])
from common import D as ROOT
@njit
def ex1(t, o, h, l, c, i0, i1, s, lv, a, tk, soft, hard, close_mode, n, far, tend):
    j = -1
    for k in range(i0, i1):
        if (s > 0 and l[k] <= lv * (1 - 0.0005)) or (s < 0 and h[k] >= lv * (1 + 0.0005)):
            j = k; break
    if j < 0: return np.nan, -1
    fill = min(lv, o[j]) if s > 0 else max(lv, o[j])
    risk = soft * a; hsl = fill - s * hard * a; ssl = fill - s * soft * a; tp = fill + s * tk * a; tp2 = fill + s * far * a
    mae = 0.0; ext = False; k = j
    while k < len(c) and t[k] < tend:
        adv = (fill - l[k]) if s > 0 else (h[k] - fill)
        if (s > 0 and l[k] <= hsl) or (s < 0 and h[k] >= hsl):
            x = o[k] if (k > j and ((s > 0 and o[k] <= hsl) or (s < 0 and o[k] >= hsl))) else hsl
            return (s * (x - fill) - (0.0007 + 0.0003 * (t[k] - t[j]) / 86400) * fill) / risk, 0
        if k > j:
            if ext:
                if (s > 0 and h[k] >= tp2) or (s < 0 and l[k] <= tp2):
                    return (s * (tp2 - fill) - (0.0004 + 0.0003 * (t[k] - t[j]) / 86400) * fill) / risk, 1
            elif (s > 0 and h[k] >= tp) or (s < 0 and l[k] <= tp):
                if n > 0 and max(mae, adv) < n * a:
                    ext = True
                else:
                    return (s * (tp - fill) - (0.0004 + 0.0003 * (t[k] - t[j]) / 86400) * fill) / risk, 1
        if close_mode > 0 and (t[k] + 60) % (close_mode * 3600) == 0 and ((s > 0 and c[k] <= ssl) or (s < 0 and c[k] >= ssl)):
            return (s * (c[k] - fill) - (0.0007 + 0.0003 * (t[k] - t[j]) / 86400) * fill) / risk, 0
        if adv > mae: mae = adv
        k += 1
    k = min(k, len(c)) - 1
    return (s * (c[k] - fill) - (0.0007 + 0.0003 * (t[k] - t[j]) / 86400) * fill) / risk, 3
M1 = {}
for f in os.listdir(f"{ROOT}/data/1mz"):
    z = np.load(f"{ROOT}/data/1mz/{f}"); M1[f[:-4]] = (z["t"].astype(np.int64), z["o"], z["h"], z["l"], z["c"])
VAR = {"закр. 1ч за 2 / авар. 3 (692)": (1.1, 2.0, 3.0, 1, 0.0, 0.0), "закр. свечи графика (4ч/2ч) / авар. 3": (1.1, 2.0, 3.0, -1, 0.0, 0.0),
       "закр. 4ч / авар. 3": (1.1, 2.0, 3.0, 4, 0.0, 0.0), "закр. свечи графика / авар. 3.5": (1.1, 2.0, 3.5, -1, 0.0, 0.0)}
res = {k: [] for k in VAR}; nn = 0
for v in EV:
    if v["sym"] not in M1 or v["t"] < ts(2024, 10) + 86400: continue
    t, o, h, l, c = M1[v["sym"]]; bs = v["tfh"] * 3600; w0 = v["t"] + bs
    i0 = int(np.searchsorted(t, w0)); i1 = int(np.searchsorted(t, w0 + 4 * bs))
    if i0 >= len(t) or t[i0] - w0 > 600: continue
    j = next((k for k in range(i0, i1) if ((l[k] <= v["lv"] * 0.9995) if v["s"] > 0 else (h[k] >= v["lv"] * 1.0005))), -1)
    if j < 0: continue
    tend = (t[j] // bs) * bs + 32 * bs; nn += 1
    for nm, (tk, soft, hard, cm, n, far) in VAR.items():
        r, k = ex1(t, o, h, l, c, i0, i1, v["s"], v["lv"], v["a"], tk, soft, hard, v["tfh"] if cm < 0 else cm, n, far, tend); res[nm].append((r, k))
print(f"сделок на минутках: {nn} (40 монет, с 10.2024, сигналы до отбора в пул)")
for nm in VAR:
    a = np.array(res[nm]); print(f"{nm:40s} {a[:, 0].mean():+.3f}R WR {np.mean(a[:, 1] == 1)*100:.0f}% стопов {np.mean(a[:, 1] == 0)*100:.0f}% · 2025: {a[:, 0][:len(a)].mean():+.3f}", flush=True)
