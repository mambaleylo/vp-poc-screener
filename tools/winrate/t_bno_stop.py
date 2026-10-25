"""v0.99.728 — no P/R / SMC / EMA position on Binance is left without its stop: (a) refused at the open -> put again on
the next tick; (b) refused for a minute -> closed at the market (+ Telegram); (c) the break-even refused because the price
is already back through the entry (-2021) -> closed at the market at once, the old stop and the take off (the old code
took the old stop off first and left the position naked)"""
import os
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "t_bn_others.py")).read().split("# (1) SMC long AAA")[0]
exec(src)
TG = []; V.send_telegram = lambda m, **k: TG.append(m)
REJ = {"mode": None}
_f = V.requests.request
def fake2(method, url, headers=None, timeout=None, **k):
    if REJ["mode"] and method == "POST" and "/fapi/v1/algoOrder" in url and "type=STOP_MARKET" in url:
        X["calls"].append((method, "/fapi/v1/algoOrder", {"rejected": REJ["mode"]}))
        if REJ["mode"] == "trigger":
            return R(400, {"code": -2021, "msg": "Order would immediately trigger."})
        return R(400, {"code": -1001, "msg": "Internal error; unable to process your request. Please try your request again."})
    return _f(method, url, headers=headers, timeout=timeout, **k)
V.requests.request = fake2
def mk(c): return [x for x in X["calls"] if x[1] == "/fapi/v1/order" and x[2].get("type") == "MARKET"]
# (a) the stop refused at the open (a network-type error), then accepted on the next tick
REJ["mode"] = "error"; X["calls"].clear()
r = V.bno_open("smc", "AAA_USDT", "LONG", 10.0, 9.5, 11.5)
rec = V._BNO["pos"]["AAA_USDT"]; q = float(mk(None)[0][2]["quantity"]); X["pos"]["AAAUSDT"] = q
a_open = r["status"] == "OPENED_TP_SL_FAILED" and not rec.get("sl_id") and rec.get("tp_id")
REJ["mode"] = None; X["calls"].clear(); V.bno_tick()
st = [a for a in X["algos"].values() if a["symbol"] == "AAAUSDT" and a["type"] == "STOP_MARKET" and a["algoStatus"] == "NEW"]
res["(a) refused at the open -> put on the next tick"] = a_open and rec.get("sl_id") and len(st) == 1 and st[0]["triggerPrice"] == "9.5" and not mk(None)
V.bno_close("smc", "AAA_USDT", "LONG"); X["pos"]["AAAUSDT"] = 0.0; V._BNO["pos"].pop("AAA_USDT", None)
# (b) refused at the open and for over a minute -> closed at the market, told
REJ["mode"] = "error"; X["calls"].clear(); TG.clear()
r = V.bno_open("smc", "AAA_USDT", "LONG", 10.0, 9.5, 11.5)
rec = V._BNO["pos"]["AAA_USDT"]; q = float(mk(None)[0][2]["quantity"]); X["pos"]["AAAUSDT"] = q
X["calls"].clear(); V.bno_tick(); first = not mk(None) and rec.get("nostop_t")
rec["nostop_t"] -= 61; X["calls"].clear(); V.bno_tick()
cm = mk(None)
res["(b) no stop for a minute -> closed at the market"] = (first and cm and cm[0][2]["side"] == "SELL" and float(cm[0][2]["quantity"]) == q
                                                          and rec.get("closed_nostop") and TG and "закрыта по рынку" in TG[-1])
X["pos"]["AAAUSDT"] = 0.0; V._BNO["pos"].pop("AAA_USDT", None)
# (c) SMC's break-even when the price is already back through the entry: -2021 -> closed at once, nothing left on the book
REJ["mode"] = None; X["calls"].clear(); TG.clear()
r = V.bno_open("smc", "AAA_USDT", "LONG", 10.0, 9.5, 11.5)
rec = V._BNO["pos"]["AAA_USDT"]; q = float(mk(None)[0][2]["quantity"]); X["pos"]["AAAUSDT"] = q
old_sl, old_tp = rec["sl_id"], rec["tp_id"]
REJ["mode"] = "trigger"; X["calls"].clear()
note = V.part_take_on_exchange("smc", {"symbol": "AAA_USDT", "side": 1, "direction": "LONG", "px": 10.0, "entry": 10.0, "sl": 9.5}, 0.0)
cm = mk(None); live = [a for a in X["algos"].values() if a["symbol"] == "AAAUSDT" and a["algoStatus"] == "NEW"]
res["(c) break-even through the entry -> closed at once"] = (cm and float(cm[0][2]["quantity"]) == q and cm[0][2]["side"] == "SELL"
                                                             and X["algos"][int(old_sl)]["algoStatus"] == "CANCELED" and X["algos"][int(old_tp)]["algoStatus"] == "CANCELED"
                                                             and not live and "закрыта по рынку" in note and TG)
# (d) the normal break-even still: the new stop at the entry, nothing closed
X["pos"]["AAAUSDT"] = 0.0; V._BNO["pos"].pop("AAA_USDT", None); REJ["mode"] = None; X["calls"].clear()
r = V.bno_open("smc", "AAA_USDT", "LONG", 10.0, 9.5, 11.5)
rec = V._BNO["pos"]["AAA_USDT"]; q = float(mk(None)[0][2]["quantity"]); X["pos"]["AAAUSDT"] = q; X["calls"].clear()
note = V.part_take_on_exchange("smc", {"symbol": "AAA_USDT", "side": 1, "direction": "LONG", "px": 10.0, "entry": 10.0, "sl": 9.5}, 0.0)
st = [a for a in X["algos"].values() if a["symbol"] == "AAAUSDT" and a["type"] == "STOP_MARKET" and a["algoStatus"] == "NEW"]
res["(d) normal break-even unchanged"] = not mk(None) and len(st) == 1 and st[0]["triggerPrice"] == "10" and rec["sl_px"] == 10.0 and "закрыта" not in note
print(" · ".join(f"{k} {v}" for k, v in res.items())); print("ALL OK" if all(bool(v) for v in res.values()) else "FAILED")
