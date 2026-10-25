"""v0.99.731 — a real ⚡ limit gone unfilled: did the price reach it (Binance 1-min candles since it went on the exchange)
and how far past it — recorded on the order (the lab: the share of touches a resting limit misses)"""
import time
from common import V
res = {}
now = int(time.time()) // 60 * 60; t0 = now - 600
logs = []; V.log_error = lambda m: logs.append(m)
def kl(lows=None, highs=None):
    return lambda s, i, a, b: [{"time": t0 + 60 * k, "open": 1.0, "high": (highs or [1.0] * 10)[k], "low": (lows or [1.0] * 10)[k], "close": 1.0} for k in range(10)]
# a long at 0.99: the low 0.9899 -> reached, 0.0101% past
V.binance_klines = kl(lows=[1.0, 1.0, 0.995, 0.9899, 0.99, 1.0, 1.0, 1.0, 1.0, 1.0])
o = {"symbol": "AAA_USDT", "side": 1, "lv": 0.99, "t0": t0 - 3600}
tn = V._dlm_touch_note(o, {"price": 0.99, "t_place": t0}, now)
res["long touched, depth and time"] = tn["reached"] and abs(tn["pen_pct"] - 0.0101) < 1e-3 and tn["t"] == t0 + 180 and any("touched but not filled" in m for m in logs)
# a short at 1.02 never reached (high 1.015)
logs.clear(); V.binance_klines = kl(highs=[1.0, 1.01, 1.015] + [1.0] * 7)
o = {"symbol": "AAA_USDT", "side": -1, "lv": 1.02, "t0": t0}
tn = V._dlm_touch_note(o, {"price": 1.02, "t_place": t0}, now)
res["short not reached -> negative depth, no log"] = (not tn["reached"]) and tn["pen_pct"] < 0 and tn["t"] is None and not logs
# no candles (Binance silent) -> nothing recorded
V.binance_klines = lambda *a: []
o = {"symbol": "AAA_USDT", "side": 1, "lv": 0.99}
res["no candles -> no record"] = V._dlm_touch_note(o, {"price": 0.99, "t_place": t0}, now) is None and "touch" not in o
print(" · ".join(f"{k} {v}" for k, v in res.items())); print("ALL OK" if all(bool(v) for v in res.values()) else "FAILED")
