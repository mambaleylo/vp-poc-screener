"""the audit of v0.99.690 "step by step on the bot's own code": the bot's dlm_scan + dlm_settle (virtual mode) replayed
over 2026 on the local Binance candles, the clock mocked (every 2h: settle, then the scans of the streams whose bar
closed — dlm_loop's order); the virtual trades it makes vs the backtest list (vp_bt_trades.json "dlm"), trade by trade.
usage: replay691.py CHUNK NCHUNKS -> replay691_W.json (v0.99.691: all the coins in one run — the side cap ties them;
the period split in chunks, each with a 7-day warm-up before it)"""
import sys; AV = list(sys.argv)
import os, json, bisect, time
os.environ["TFH"] = "4"
from common import V
import s23_engine as E4
import s21h2_engine as E2
W, NW = int(AV[1]), int(AV[2])
A0, B0 = 1780272000, 1792540800   # 2026-06-01 .. 2026-10-20
CH = (B0 - A0) // NW // 7200 * 7200
CA = A0 + W * CH; CB = B0 if W == NW - 1 else CA + CH
START, END = CA - 7 * 86400, CB
def bname(gs):
    b = gs.replace("_USDT", "")
    for c, scl in ((b + "USDT", 1.0), ("1000" + b + "USDT", 1000.0)):
        if os.path.exists(f"s23_4h/{c}.npz") or os.path.exists(f"s23_4hx/{c}.npz"): return c, scl
    return None, None
coins = [c for c in V.RESEARCH_COINS_211 if c != "USDC_USDT" and bname(c)[0]]
mine = sorted(coins)
SER = {}
def series(gs, tf):
    if (gs, tf) not in SER:
        src, scl = ("BTCUSDT", 1.0) if gs == "BTC_USDT" else bname(gs)
        T, O, H, L, C, Vv = (E2 if tf == "2h" else E4).load15(src)
        b = [{"time": int(t), "open": o / scl, "high": h / scl, "low": l / scl, "close": c / scl, "volume": v, "bn": True} for t, o, h, l, c, v in zip(T, O, H, L, C, Vv)]
        SER[(gs, tf)] = (b, [x["time"] for x in b])
    return SER[(gs, tf)]
def fake_closed(sym, tf, sec, n, now):
    b, T = series(sym, tf); j = bisect.bisect_right(T, now - sec)
    return b[max(0, j - n):j]
def fake_bars(sym, start, now, bs=900):
    b, T = series(sym, {7200: "2h", 14400: "4h"}[bs]); i = bisect.bisect_left(T, start); j = bisect.bisect_right(T, now - bs)
    return b[i:j]
from fasttree import fast_tree_pred   # the bot's zm_tree_pred compiled (checked: identical to the bit)
V.zm_tree_pred = fast_tree_pred
V._dlm_closed = fake_closed; V._dlm_bars = fake_bars; V.dlm_coins = lambda: mine
V.dlm_save = lambda: None; V.heartbeat = lambda *a, **k: None; V.send_telegram = lambda *a, **k: None
V.AUTOTRADE_ENABLED_DLM = False; V.TELEGRAM_ALERTS_DLM = False
V.log_error = lambda m: print("ERR", m, flush=True)
m = V.dlm_model(); streams = V._dlm_streams(m)
V._DLM.update({"orders": [], "trades": []})
ALL = []   # every order the scans made (filled or not) — for the real-mode rules
_scan = V.dlm_scan
def scan_log(t_bar, st):
    n0 = {o["id"] for o in V._DLM["orders"]}
    _scan(t_bar, st)
    ALL.extend(dict(o) for o in V._DLM["orders"] if o["id"] not in n0)
V.dlm_scan = scan_log
t0 = time.time()
for t in range(START, END, 7200):
    V.dlm_settle(t + 30)
    for st in streams:
        if t % int(st["bar_sec"]) == 0:
            V.dlm_scan(t, st)
    if (t - START) % (86400 * 10) == 0:
        print(W, time.strftime("%Y-%m-%d", time.gmtime(t)), len(V._DLM["trades"]), f"{time.time() - t0:.0f}s", flush=True)
V.dlm_settle(END + 30)
json.dump({"coins": mine, "trades": V._DLM["trades"], "orders": ALL, "from": CA, "to": CB}, open(f"replay691_{W}.json", "w"))
print("done", W, len(V._DLM["trades"]), flush=True)
