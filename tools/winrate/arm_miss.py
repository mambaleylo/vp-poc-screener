"""⚡ live arming vs the backtest: the bot puts a limit on the exchange only once the price is within 0.3 ATR of it (5 s
polls, paused while the 2h / 4h scans run at the bar closes) — a fast spike through the level is missed. On Binance 1m
candles (40 coins, the backtest list's trades): the touch minute; "caught" if a minute before it closed within 0.3 ATR
of the level (the poll sees it) or the touch minute opened within 0.3 ATR; the touches in the first k minutes after a
2h close (the scan running) apart; the R of the caught / missed trades"""
import os, json, numpy as np
from common import D as ROOT
from mk import ts
B = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))["dlm"]
M1 = {}
for f in os.listdir(f"{ROOT}/data/1mz"):
    z = np.load(f"{ROOT}/data/1mz/{f}"); M1[f[:-4]] = (z["t"].astype(np.int64), z["o"], z["h"], z["l"], z["c"])
def bsym(gs):
    b = gs.replace("_USDT", "")
    for c, scl in ((b + "USDT", 1.0), ("1000" + b + "USDT", 1000.0)):
        if c in M1: return c, scl
    return None, None
rows = []
for tr in B:
    c_, scl = bsym(tr["s"])
    if not c_ or tr.get("r") is None: continue
    t, o, h, l, c = M1[c_]
    s = tr["d"]; lv = tr["lv"] * scl; atr = abs(tr["e"] - tr["sl"]) * scl / 2
    bs = 7200 if tr["c"] == "2h" else 14400
    a0 = tr["t"]; a1 = a0 + 4 * bs   # the order's life
    i0 = int(np.searchsorted(t, a0)); i1 = int(np.searchsorted(t, a1))
    if i0 >= len(t) or t[i0] - a0 > 600: continue
    k = next((k for k in range(i0, i1) if ((l[k] <= lv) if s > 0 else (h[k] >= lv))), -1)
    if k < 0: continue
    d = lambda p: s * (p - lv) / atr   # > 0: not reached
    prev_close_d = d(c[k - 1]) if k > i0 else 9.0
    open_d = d(o[k])
    seen = (prev_close_d <= 0.3) or (open_d <= 0.3)
    since = (t[k] % 7200) / 60   # minutes after a 2h close
    rows.append((tr["r"], seen, since < 5, open_d, prev_close_d))
a = np.array(rows, dtype=float)
R, seen, early = a[:, 0], a[:, 1] > 0, a[:, 2] > 0
print(f"сделок с минутками {len(a)}")
print(f"бот увидел бы цену в 0.3 ATR до касания: {seen.mean()*100:.0f}% · R этих {R[seen].mean():+.3f} (WR {np.mean(R[seen] > 0)*100:.0f}%) · пропущенных {R[~seen].mean():+.3f} (WR {np.mean(R[~seen] > 0)*100:.0f}%)")
print(f"касание в первые 5 мин после закрытия 2ч (идёт пересчёт): {early.mean()*100:.0f}% · из них увидел бы: {seen[early].mean()*100:.0f}%")
for thr in (0.5, 1.0, 1.5, 2.0):
    sn = (a[:, 4] <= thr) | (a[:, 3] <= thr)
    print(f"  выставлять за {thr} ATR: поймано {sn.mean()*100:.0f}% · R пойманных {R[sn].mean():+.3f}")
