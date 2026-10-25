"""v0.99.729 — P/R / SMC / EMA trading on Binance go by Binance: the live prices (the level's touch, P/R's entry / stop /
take, EMA's +1R) and the candles their trades are walked on (the take / stops / break-even) are Binance's, Gate's only
as a fallback / when not trading there; a record closed by its walk with the Binance position still open -> that
position closed at the market too"""
import time
from common import V
res = {}
V.get_tickers = lambda: [{"contract": "AAA_USDT", "last": "10.0"}, {"contract": "PEPE_USDT", "last": "0.0000100"}, {"contract": "GATEONLY_USDT", "last": "5"}]
V.bnf_prices = lambda: {"AAAUSDT": 10.4, "1000PEPEUSDT": 0.0123}
routed = {"v": True}; V.bn_routed = lambda m: routed["v"]
px = V.mod_px_map("smc")
res["prices: Binance's (1000-coins scaled), Gate's for the rest"] = (px["AAA_USDT"] == 10.4 and abs(px["PEPE_USDT"] - 0.0000123) < 1e-12 and px["GATEONLY_USDT"] == 5.0)
routed["v"] = False; px = V.mod_px_map("smc")
res["not on Binance: Gate's"] = px["AAA_USDT"] == 10.0
calls = []
V.binance_klines = lambda s, i, a, b: (calls.append(("bn", s)), [{"time": a, "open": 1, "high": 2, "low": 0.5, "close": 1.5}, {"time": a + 3600, "open": 1, "high": 2, "low": 1, "close": 1, "forming": True}])[1]
V.get_candles_range = lambda s, i, a, b: (calls.append(("gate", s)), [{"time": a, "open": 9, "high": 9, "low": 9, "close": 9}])[1]
routed["v"] = True; cs = V.mod_candles("smc", "AAA_USDT", "1h", 0, 7200)
res["candles: Binance's, the forming one out"] = len(cs) == 1 and cs[0]["high"] == 2 and calls[-1][0] == "bn"
V.binance_klines = lambda s, i, a, b: []
cs = V.mod_candles("smc", "AAA_USDT", "1h", 0, 7200)
res["Binance empty -> Gate's"] = cs and cs[0]["open"] == 9
routed["v"] = False; calls.clear(); V.mod_candles("smc", "AAA_USDT", "1h", 0, 7200)
res["not on Binance -> Gate's"] = calls and calls[-1][0] == "gate"
# the record closed by the walk (the take reached on the candles) while the Binance position is still open -> closed
routed["v"] = True
h0 = int(time.time()) // 3600 * 3600 - 5 * 3600
V.mod_candles = lambda mode, s, i, a, b: [{"time": h0, "open": 10, "high": 10.1, "low": 9.9, "close": 10}, {"time": h0 + 3600, "open": 10, "high": 11.6, "low": 10, "close": 11.5}]
V._BNO["pos"]["AAA_USDT"] = {"mode": "smc", "bsym": "AAAUSDT", "side": 1, "qty": 5, "entry": 10.0, "step": 0.001, "dual": False}
V.bnf_positions = lambda: {"AAAUSDT": [{"amt": 5.0, "mark": 11.4}]}
closed = []; V.close_position_for_mode = lambda m, s, d: (closed.append((m, s, d)), {"ok": True})[1]
V.AUTOTRADE_ENABLED_SMC = True; V.smc_save = lambda: None; V.notify_trade_result = lambda *a, **k: None
V._SMC["armed"] = []; V._SMC["armed_at"] = None
V._SMC["trades"] = [{"id": "s", "symbol": "AAA_USDT", "side": 1, "direction": "LONG", "entry": 10.0, "sl": 9.5, "tp": 11.5, "hs": 9.0, "ch": 4,
                     "hour": h0, "hold": 96, "status": "OPEN", "real": True, "rv": V.SMC_MODEL_VER}]
V.smc_settle()
t = V._SMC["trades"][0]
res["record WIN + the Binance position still open -> closed too"] = t["status"] == "CLOSED" and t["result"] == "WIN" and closed == [("smc", "AAA_USDT", "LONG")]
V.bnf_positions = lambda: {}
closed.clear(); t.update(status="OPEN", result=None); V.smc_settle()
res["position already gone -> nothing sent"] = V._SMC["trades"][0]["status"] == "CLOSED" and not closed
print(" · ".join(f"{k} {v}" for k, v in res.items())); print("ALL OK" if all(bool(v) for v in res.values()) else "FAILED")
