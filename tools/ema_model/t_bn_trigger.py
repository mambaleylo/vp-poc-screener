"""v0.99.669: a limit reached by Binance's 1-min wick (Gate's price never there) fires the EMA level and opens the trade at
Gate's market; Gate's price a whole R past the limit = signal only; no Binance answer = Gate's price alone; P/R / Neuro /
breakout use the same check"""
import types, time
from common import V as vp
NOW = [1790172000 + 600.0]
vp.time = types.SimpleNamespace(**{k: getattr(time, k) for k in ("sleep", "strftime", "gmtime", "localtime", "monotonic", "perf_counter")}, time=lambda: NOW[0])
BN = {"IOUSDT": [(1790172000 + 480, 0.1368, 0.1440)]}
class Resp:
    def __init__(s, code, js): s.status_code, s._js = code, js
    def json(s): return s._js
def fake_get(url, params=None, timeout=None):
    rows = BN.get(params["symbol"])
    if rows is None: return Resp(400, {})
    return Resp(200, [[t * 1000, "0", str(hi), str(lo), "0", "0"] for t, lo, hi in rows])
vp.requests = types.SimpleNamespace(get=fake_get)
GATE = {"IO_USDT": 0.1430}
vp.get_tickers = lambda *a, **k: [{"contract": c, "last": str(p)} for c, p in GATE.items()]
calls = []
vp.execute_autotrade = lambda mode, sym, d, px, sl, tp, **k: calls.append((mode, sym, px, sl, tp)) or {"status": "OPENED"}
for f in ("emx_save", "send_telegram", "notify_trade_result"): setattr(vp, f, lambda *a, **k: None)
vp.emx_coin_ok = lambda s: True
vp.AUTOTRADE_ENABLED_EMW = True
a = {"symbol": "IO_USDT", "tf": "1d", "n": 14, "side": 1, "lv": 0.137852, "ema": 0.13975, "sl": 0.130817, "tp": 0.165995, "score": 0.5, "hour": 1790172000, "sel": True}
vp._EMX.update({"armed": [a], "armed_at": 1790172000, "trades": [], "model": {"rule": {"hold_h": 72, "part_r": 1.0, "part_f": 0.33}}})
vp.emx_watch_tick()
tr = vp._EMX["trades"]
assert len(tr) == 1 and tr[0]["trig"] == "binance" and tr[0]["real"] and calls[0][2] == 0.1430, (tr, calls)
print("1. Binance wick -> fired, Gate market at", calls[0][2], "trig", tr[0]["trig"])
# 2. Gate a whole R past the limit: a signal, no real trade
GATE["IO_USDT"] = 0.137852 + 0.008; calls.clear(); vp._EMX["trades"] = []; vp._BN_REC.clear()
vp.emx_watch_tick(); tr = vp._EMX["trades"]
assert len(tr) == 1 and not tr[0]["real"] and tr[0].get("late") and not calls, (tr, calls)
print("2. too late on Gate -> signal only, late", tr[0]["late"])
# 3. no Binance (unknown coin), Gate above the limit -> nothing; Gate at the limit -> fired by gate
BN.clear(); vp._BN_REC.clear(); vp._BN_MISS.clear(); GATE["IO_USDT"] = 0.1430; vp._EMX["trades"] = []; calls.clear()
vp.emx_watch_tick(); assert not vp._EMX["trades"], vp._EMX["trades"]
GATE["IO_USDT"] = 0.1375; vp.emx_watch_tick(); tr = vp._EMX["trades"]
assert len(tr) == 1 and tr[0]["trig"] == "gate" and calls[0][2] == 0.1375, (tr, calls)
print("3. no Binance: Gate's price alone works")
# 4. an old Binance wick (before the hour) does not count
BN["IOUSDT"] = [(1790172000 - 120, 0.1368, 0.144)]; vp._BN_REC.clear(); vp._BN_MISS.clear()
assert vp.limit_touched("IO_USDT", 1, 0.137852, 0.1430, 1790172000) is None
BN["IOUSDT"] = [(1790172000 + 540, 0.1368, 0.144)]; vp._BN_REC.clear()
assert vp.limit_touched("IO_USDT", 1, 0.137852, 0.1430, 1790172000) == "binance"
assert vp.limit_touched("IO_USDT", -1, 0.1439, 0.1430, 1790172000) == "binance"
print("4. the window and the short side: ok")
# 5. P/R pending trade fired by Binance
vp.AUTOTRADE_ENABLED_PRV = True; calls.clear(); GATE["IO_USDT"] = 0.1430
vp._PRX.update({"model": {"rule": {"stop_atr": 3.0, "hard_atr": 6.0, "take_r": 1.5}}, "trades": [{"id": "p", "symbol": "IO_USDT", "side": 1, "direction": "LONG",
               "status": "PENDING", "lv": 0.1379, "hour": 1790172000, "wait": 3, "atr": 0.002, "tf": 1, "score": 1}]})
vp.prx_save = lambda *a, **k: None
vp.prx_watch_tick(); t = vp._PRX["trades"][0]
assert t.get("trig") == "binance" and calls and calls[0][0] == "prv", (t, calls)
print("5. P/R by Binance's wick: ok")
print("all ok")
