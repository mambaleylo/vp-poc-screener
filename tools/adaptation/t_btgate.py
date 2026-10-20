"""v0.99.648 — the Gate re-walk on BINANCE candles must give back the backtest's own R (the walk = the research's rule)."""
import time
from common import V, load
V.BT_TRADES_FILE = "/home/user/vp-poc-screener/vp_bt_trades.json"
import os; os.utime(V.BT_TRADES_FILE, None)
CACHE = {}
def rng(sym, tf, a, b):
    base = sym.replace("_USDT", "")
    for s in (base + "USDT", "1000" + base + "USDT"):
        if s not in CACHE:
            CACHE[s] = load(s)
        if CACHE[s]:
            sc = 1000.0 if s.startswith("1000") else 1.0
            h1 = [dict(c, open=c["open"] / sc, high=c["high"] / sc, low=c["low"] / sc, close=c["close"] / sc) for c in CACHE[s]] if sc != 1 else CACHE[s]
            bars = h1 if tf == "1h" else V._oc_agg(h1, {"4h": 4, "1d": 24}[tf])
            return [c for c in bars if a <= c["time"] <= b]
    return []
V.get_candles_range = rng
now = time.time
V.time.time = lambda: 1790900000   # the data's end (Binance history up to 2026-09)
for mod in ("prv", "emx", "rbx"):
    V.bt_gate_check(mod, months=12)
    print(mod, V._BTG[mod])
