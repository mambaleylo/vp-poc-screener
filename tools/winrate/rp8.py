"""⚡ (the bot's dlm_scan + dlm_settle, virtual) replayed over 2026-01 .. 2026-10 on the local Binance 1h candles for a coin
group: base (the bot's 210), new150 (not in the bot, >= 150M $ a month in 2026), new50 (50–150M), all (base + new150).
The model trained to 2025-12-29 -> 2026 out of sample. usage: rp.py GROUP CHUNK NCHUNKS -> rp_GROUP_CHUNK.json"""
import sys; AV = list(sys.argv)
import os, json, bisect, time
import numpy as np
from common import V
A0, B0 = 1767225600, 1790812800
G, CA, CB = AV[1], int(AV[2]), int(AV[3])   # rp8: the period given exactly (the missing parts of the 4-chunk run)
W = f"{CA}"
START, END = (CA - 7 * 86400) // 14400 * 14400, CB   # the loop on the 2h / 4h bars (CA itself only filters)
U = json.load(open("universe.json")); H0 = 1759276800
def bname(gs):
    b = gs.replace("_USDT", "")
    for c, scl in ((b + "USDT", 1.0), ("1000" + b + "USDT", 1000.0)):
        if os.path.exists(f"data/1h/{c}.csv"): return c, scl
    return None, None
base = [c for c in V.RESEARCH_COINS_211 if c != "USDC_USDT" and bname(c)[0]]
def gsn(b): return b[:-4] + "_USDT"
newc = [(gsn(r[0]), r[4]) for r in U if not r[1] and r[2] <= H0 and r[3] >= B0 - 3 * 86400]
new150 = [c for c, v in newc if v >= 150e6]; new50 = [c for c, v in newc if 50e6 <= v < 150e6]
mine = sorted({"base": base, "new150": new150, "new50": new50, "all": base + new150}[G])
RAW = {}
def raw(gs):
    if gs not in RAW:
        src, scl = ("BTCUSDT", 1.0) if gs == "BTC_USDT" else bname(gs)
        a = np.loadtxt(f"data/1h/{src}.csv", delimiter=",", ndmin=2)
        t = a[:, 0].astype(np.int64); k = np.concatenate([[True], np.diff(t) > 0]); a = a[k]
        RAW[gs] = (a[:, 0].astype(np.int64), a[:, 1] / scl, a[:, 2] / scl, a[:, 3] / scl, a[:, 4] / scl, a[:, 5])
    return RAW[gs]
SER = {}
def series(gs, tf):
    if (gs, tf) not in SER:
        T, O, H, L, C, Vv = raw(gs); hh = {"4h": 4, "2h": 2, "1h": 1}[tf]
        # the depth the bot looks at (dlm_scan: 3000 4h / 4500 2h bars; the 1h only from the trades' days) — the memory
        k0 = bisect.bisect_left(T, START - {"4h": 510, "2h": 385, "1h": 15}[tf] * 86400)
        T, O, H, L, C, Vv = T[k0:], O[k0:], H[k0:], L[k0:], C[k0:], Vv[k0:]
        blk = T // (hh * 3600); st = np.concatenate([[0], np.flatnonzero(blk[1:] != blk[:-1]) + 1]); en = np.concatenate([st[1:], [len(T)]])
        full = (en - st) == hh; st, en = st[full], en[full]
        b = [{"time": int(blk[s] * hh * 3600), "open": float(O[s]), "high": float(H[s:e].max()), "low": float(L[s:e].min()), "close": float(C[e - 1]),
              "volume": float(Vv[s:e].sum()), "bn": True} for s, e in zip(st, en)]
        SER[(gs, tf)] = (b, [x["time"] for x in b])
    return SER[(gs, tf)]
def fake_closed(sym, tf, sec, n, now):
    b, T = series(sym, tf); j = bisect.bisect_right(T, now - sec)
    return b[max(0, j - n):j]
def fake_bars(sym, start, now, bs=900):
    b, T = series(sym, {7200: "2h", 14400: "4h"}[bs]); i = bisect.bisect_left(T, start); j = bisect.bisect_right(T, now - bs)
    return b[i:j]
def fake_range(sym, tf, a, b):
    T, O, H, L, C, Vv = raw(sym); i, j = bisect.bisect_left(T, a), bisect.bisect_right(T, b)
    return [{"time": int(T[k]), "open": float(O[k]), "high": float(H[k]), "low": float(L[k]), "close": float(C[k])} for k in range(i, j)]
def fake_1h(sym, a, now):
    return [c for c in fake_range(sym, "1h", a, now) if c["time"] + 3600 <= now]
from fasttree import fast_tree_pred
V.zm_tree_pred = fast_tree_pred
V.get_candles_range = fake_range
V._dlm_closed = fake_closed; V._dlm_bars = fake_bars; V.dlm_coins = lambda: mine
V.bn_closed = lambda sym, tf, sec, n, now: fake_closed(sym, tf, sec, n, now)
V.dlm_save = lambda: None; V.heartbeat = lambda *a, **k: None; V.send_telegram = lambda *a, **k: None
V.AUTOTRADE_ENABLED_DLM = False; V.TELEGRAM_ALERTS_DLM = False; V.DLM_BINANCE = True
V.log_error = lambda m: print("ERR", m[:200], flush=True)
m = V.dlm_model(); streams = V._dlm_streams(m)
V._DLM.update({"orders": [], "trades": []})
t0 = time.time()
for t in range(START, END, 7200):
    V.dlm_settle(t + 30)
    for st in streams:
        if t % int(st["bar_sec"]) == 0:
            V.dlm_scan(t, st)
    if (t - START) % (86400 * 10) == 0:
        print(G, W, time.strftime("%Y-%m-%d", time.gmtime(t)), len(V._DLM["trades"]), f"{time.time() - t0:.0f}s", flush=True)
V.dlm_settle(END + 30 + 40 * 86400)
json.dump({"coins": mine, "trades": V._DLM["trades"], "from": CA, "to": CB}, open(f"rp_{G}8_{W}.json", "w"))
print("done", G, W, len(V._DLM["trades"]), f"{time.time() - t0:.0f}s", flush=True)
