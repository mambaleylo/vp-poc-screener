"""the user: "стопы почти все выбиваются фитилем". The stopped trades of the backtest list (2025–26): the 1h candle of
the stop closed back inside (a wick) or beyond; hours from the fill; did the price reach the take 1 ATR later in the
trade's time"""
import os, json, numpy as np, collections
os.environ["TFH"] = "1"
import s19h_engine as E1
L_ = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))["dlm"]
def bname(gs):
    b = gs.replace("_USDT", "")
    for c, scl in ((b + "USDT", 1.0), ("1000" + b + "USDT", 1000.0)):
        if os.path.exists(f"data_1h_ok") or True:
            try:
                T, O, H, L, C, V = E1.load15(c); return T.astype(np.int64), O / scl, H / scl, L / scl, C / scl
            except Exception: pass
C1 = {}
st = [x for x in L_ if x["k"] == "stop"]
res = collections.Counter(); hrs = []; later = 0; later_cl = 0; sameh = 0; deep = []
for x in st:
    if x["s"] not in C1: C1[x["s"]] = bname(x["s"])
    T, O, H, L, C = C1[x["s"]]; s = x["d"]; sl = x["sl"]; e = x["e"]; a = abs(e - sl) / 2; tp1 = e + s * a
    i0 = int(np.searchsorted(T, x["f"])); i1 = int(np.searchsorted(T, x["x"] + 32 * 4 * 3600))
    fi = next((b for b in range(i0, min(i1, len(T))) if ((L[b] <= x["lv"]) if s > 0 else (H[b] >= x["lv"]))), i0)
    sb = next((b for b in range(fi, min(i1, len(T))) if ((L[b] <= sl) if s > 0 else (H[b] >= sl))), None)
    if sb is None: res["стоп не найден на 1ч"] += 1; continue
    wick = (C[sb] > sl) if s > 0 else (C[sb] < sl)
    res["фитиль (час закрылся обратно)" if wick else "закрытие за стопом"] += 1
    hrs.append(sb - fi); sameh += sb == fi
    deep.append(((sl - L[sb]) if s > 0 else (H[sb] - sl)) / a)
    end = int(np.searchsorted(T, x["f"] + 32 * (7200 if x["c"] == "2h" else 14400)))
    if any(((H[b] >= tp1) if s > 0 else (L[b] <= tp1)) for b in range(sb + 1, min(end, len(T)))):
        later += 1; later_cl += wick
n = sum(v for k, v in res.items() if k != "стоп не найден на 1ч")
print(f"стоповых сделок {len(st)} из {len(L_)}: " + ", ".join(f"{k} {v} ({v/max(n,1)*100:.0f}%)" for k, v in res.items()))
h = np.array(hrs); print(f"часов от входа до стопа: в том же часе {sameh/n*100:.0f}%, ≤4 ч {np.mean(h <= 4)*100:.0f}%, ≤12 ч {np.mean(h <= 12)*100:.0f}%, медиана {np.median(h):.0f} ч")
d = np.array(deep); print(f"как далеко прокол ушёл за стоп (в ATR): медиана {np.median(d):.2f}, четверть глубже {np.percentile(d, 75):.2f}")
print(f"после стопа цена дошла до тейка 1 ATR за время сделки: {later} ({later/n*100:.0f}% стопов), из фитильных {later_cl}")
