"""v0.99.684 — ⚡ on Binance against a fake Binance USDⓈ-M API (signature checked): the key check with the balance, the
limit (isolated, leverage from the brackets, the price and the size snapped, a 1000-coin scaled), the fill -> the
STOP_MARKET (Algo API) + the reduce-only take limit, the take -> WIN, the stop -> LOSS, the time exit at the market, an
unfilled limit expired, the free margin scaling the risk, the minimum notional, the old order endpoint when the Algo API
is missing, a hedge-mode account, the position cap (v0.99.687), the settings and the keys file"""
import sys, os, time, json, hmac, hashlib, tempfile
from urllib.parse import urlsplit, parse_qsl
from common import V

KEY, SEC = "k" * 64, "s" * 64
X = {"orders": {}, "algos": {}, "pos": {}, "next": 100, "calls": [], "wallet": 1000.0, "free": 1000.0, "dual": False, "dual_lock": False,
     "algo_api": True, "mtype": {}, "lev": {}}
INFO = {"AAAUSDT": (0.001, 0.1, 0.1, 5.0), "1000PEPEUSDT": (0.0000001, 1.0, 1.0, 5.0), "BBBUSDT": (0.01, 1.0, 1.0, 5.0), "CCCUSDT": (0.001, 1.0, 1.0, 5.0), "EEEUSDT": (0.001, 0.1, 0.1, 5.0), "FFFUSDT": (0.001, 0.1, 0.1, 5.0)}


class R:
    def __init__(self, code, j):
        self.status_code, self._j, self.text = code, j, json.dumps(j)
    def json(self):
        return self._j
    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError(self.status_code)


def oid():
    X["next"] += 1
    return X["next"]


def fake(method, url, headers=None, timeout=None, **k):
    u = urlsplit(url)
    path, qs = u.path, u.query
    p = dict(parse_qsl(qs))
    if path == "/fapi/v1/time":
        return R(200, {"serverTime": int(time.time() * 1000) + 1500})
    if path == "/fapi/v1/exchangeInfo":
        return R(200, {"symbols": [{"symbol": s, "status": "TRADING", "contractType": "PERPETUAL", "filters": [
            {"filterType": "PRICE_FILTER", "tickSize": f"{t:.10f}"}, {"filterType": "LOT_SIZE", "stepSize": str(st), "minQty": str(mq)},
            {"filterType": "MIN_NOTIONAL", "notional": str(mn)}]} for s, (t, st, mq, mn) in INFO.items()]})
    if path == "/fapi/v1/ticker/price":
        return R(200, [{"symbol": s, "price": str(v)} for s, v in X.get("px", {}).items()])
    # signed
    if "signature" in p:
        body = qs[:qs.index("&signature=")]
        if hmac.new(SEC.encode(), body.encode(), hashlib.sha256).hexdigest() != p["signature"] or (headers or {}).get("X-MBX-APIKEY") != KEY:
            return R(401, {"code": -2015, "msg": "Invalid API-key, IP, or permissions for action."})
        if abs(int(p["timestamp"]) - (time.time() * 1000 + 1500)) > 1000:
            return R(400, {"code": -1021, "msg": "Timestamp outside recvWindow"})
    X["calls"].append((method, path, p))
    if path == "/sapi/v1/account/apiRestrictions":
        return R(200, {"enableFutures": True, "enableWithdrawals": False, "ipRestrict": False, "enableReading": True})
    if path in ("/fapi/v3/account", "/fapi/v2/account"):
        return R(200, {"totalWalletBalance": str(X["wallet"]), "totalMarginBalance": str(X["wallet"]), "availableBalance": str(X["free"]), "totalUnrealizedProfit": "0"})
    if path in ("/fapi/v3/positionRisk",):
        return R(200, [{"symbol": s, "positionAmt": str(a), "entryPrice": str(X.get("entry", {}).get(s, 1)), "markPrice": str(X.get("mark", {}).get(s, 1)), "positionSide": "BOTH"}
                       for s, a in X["pos"].items() if a])
    if path == "/fapi/v1/positionSide/dual":
        if method == "GET":
            return R(200, {"dualSidePosition": X["dual"]})
        if X["dual_lock"]:
            return R(400, {"code": -4068, "msg": "position side cannot be changed if there exists position"})
        X["dual"] = p["dualSidePosition"] == "true"
        return R(200, {"code": 200, "msg": "success"})
    if path == "/fapi/v1/leverageBracket":
        return R(200, [{"symbol": p["symbol"], "brackets": [
            {"bracket": 1, "initialLeverage": 50, "notionalCap": 5000, "notionalFloor": 0, "maintMarginRatio": 0.01, "cum": 0},
            {"bracket": 2, "initialLeverage": 20, "notionalCap": 25000, "notionalFloor": 5000, "maintMarginRatio": 0.025, "cum": 75}]}])
    if path == "/fapi/v1/marginType":
        if X["mtype"].get(p["symbol"]) == "ISOLATED":
            return R(400, {"code": -4046, "msg": "No need to change margin type."})
        X["mtype"][p["symbol"]] = p["marginType"]
        return R(200, {"code": 200})
    if path == "/fapi/v1/leverage":
        if X.get("lev_cap") and int(p["leverage"]) > X["lev_cap"]:   # v0.99.713 — a new futures account
            return R(400, {"code": -4300, "msg": "You can start trading with more than 20x leverage by 2026-11-21 09:13 (UTC), because higher leverage is available 30 days after Futures account registration."})
        X["lev"][p["symbol"]] = int(p["leverage"])
        return R(200, {"leverage": int(p["leverage"])})
    if path == "/fapi/v1/order":
        if method == "POST":
            if p["type"] in ("STOP_MARKET", "TAKE_PROFIT_MARKET") and X["algo_api"]:
                return R(400, {"code": -4120, "msg": "Order type not supported for this endpoint. Please use the Algo Order API endpoints instead."})
            if X["dual"] and "reduceOnly" in p:
                return R(400, {"code": -1106, "msg": "Parameter 'reduceonly' sent when not required."})
            i = oid()
            X["orders"][i] = dict(p, orderId=i, status="NEW", executedQty="0", avgPrice="0")
            if p["type"] == "MARKET":
                X["pos"][p["symbol"]] = 0.0
                X["orders"][i].update(status="FILLED", executedQty=p["quantity"])
            return R(200, X["orders"][i])
        o = X["orders"].get(int(p["orderId"]))
        if not o:
            return R(400, {"code": -2013, "msg": "Order does not exist."})
        if method == "DELETE":
            if o["status"] in ("NEW", "PARTIALLY_FILLED"):
                o["status"] = "CANCELED"
            else:
                return R(400, {"code": -2011, "msg": "Unknown order sent."})
        return R(200, o)
    if path == "/fapi/v1/openOrders":   # v0.99.708
        return R(200, [dict(o, origQty=o.get("quantity"), clientOrderId=o.get("newClientOrderId", "")) for o in X["orders"].values() if o["status"] in ("NEW", "PARTIALLY_FILLED")])
    if path == "/fapi/v1/openAlgoOrders":
        return R(200, [dict(a, orderType=a["type"]) for a in X["algos"].values() if a["algoStatus"] == "NEW"])
    if path == "/fapi/v1/algoOrder":
        if not X["algo_api"]:
            return R(404, {"code": -5000, "msg": "Path not found"})
        if method == "POST":
            i = oid()
            X["algos"][i] = dict(p, algoId=i, algoStatus="NEW")
            return R(200, X["algos"][i])
        a = X["algos"].get(int(p["algoId"]))
        if not a:
            return R(400, {"code": -2013, "msg": "Order does not exist."})
        if method == "DELETE":
            if a["algoStatus"] == "NEW":
                a["algoStatus"] = "CANCELED"
            else:
                return R(400, {"code": -2011, "msg": "Unknown order sent."})
        return R(200, a)
    return R(404, {"code": -5000, "msg": "Path not found " + path})


V.requests.request = fake
V.requests.get = lambda url, params=None, timeout=None, **k: fake("GET", url + (("?" + "&".join(f"{a}={b}" for a, b in params.items())) if params else ""))
V.BINANCE_CREDENTIALS_FILE = os.path.join(tempfile.mkdtemp(), "bn.json")
V.dlm_save = lambda: None
V.notify_trade_result = lambda *a, **k: None
TG = []; V.send_telegram = lambda msg, *a, **k: TG.append(msg); V.TELEGRAM_ALERTS_DLM = True   # v0.99.705
V.log_error = lambda m: print("   log:", m) if "binance algo" not in m and "binance one-way" not in m else None
V._BNC[("AAA_USDT", "4h")] = {"bsym": "AAAUSDT", "scl": 1.0, "cols": [[]] * 6}
V._BNC[("PEPE_USDT", "2h")] = {"bsym": "1000PEPEUSDT", "scl": 1000.0, "cols": [[]] * 6}
V._BNC[("BBB_USDT", "4h")] = {"bsym": "BBBUSDT", "scl": 1.0, "cols": [[]] * 6}
V._BNC[("EEE_USDT", "4h")] = {"bsym": "EEEUSDT", "scl": 1.0, "cols": [[]] * 6}; V._BNC[("FFF_USDT", "4h")] = {"bsym": "FFFUSDT", "scl": 1.0, "cols": [[]] * 6}   # v0.99.715
V._DLM["model"] = {"rule": {"stop_atr": 2.0, "take_atr": 1.0, "hold_bars": 32, "alive_bars": 4, "bar_sec": 14400}}   # v0.99.687 — the 4h rule
res = {}

# (1) the keys: saved chmod 600, the check shows the balance and the rights
r = V.app.test_client().post("/api/binance/credentials", json={"api_key": KEY, "api_secret": SEC}).get_json()
c = r.get("check") or {}
res["keys + check"] = (r["ok"] and oct(os.stat(V.BINANCE_CREDENTIALS_FILE).st_mode)[-3:] == "600" and c.get("ok")
                       and c["balance"]["equity"] == 1000 and c["rights"]["futures"] and not c["rights"]["withdraw"] and c["dual"] is False)
bad = V.BINANCE_API_SECRET; V.BINANCE_API_SECRET = "x" * 64
c2 = V.binance_check(); V.BINANCE_API_SECRET = bad; V.binance_check()
res["wrong secret -> told"] = (not c2["ok"]) and "ключ не принят" in c2.get("err", "")

# (2) the limit: isolated, the leverage, the price / size snapped, the loss at the stop = the risk
V.apply_settings({"dlm_binance": True, "autotrade_dlm2": True, "risk_pct_dlm2": 10}); V.AUTOTRADE_DRY_RUN = False
res["settings"] = V.DLM_BINANCE and V.AUTOTRADE_ENABLED_DLM and V.get_settings()["dlm_binance"] is True and V.dlm_risk() == 10
now = time.time(); tb = int(now // 14400 * 14400)
mk = lambda sym, side, lv, atr: {"id": f"dlm_{sym}_{side}_{tb}_{lv}", "symbol": sym, "side": side, "lv": lv, "atr": atr, "score": 0.1, "t0": tb, "bs": 14400,
                                 "until": tb + 4 * 14400, "px": lv + side * 2 * atr, "status": "OPEN", "real": None}
V._DLM.update({"orders": [], "trades": []})
a = mk("AAA_USDT", 1, 10.0, 0.1); V._DLM["orders"].append(a)
V.dlm_real_place(a)
ra = a["real"]; o = X["orders"].get(int(ra.get("id") or 0)) or {}
loss = float(o.get("quantity", 0)) * (10.0 - 9.8)
res["limit placed"] = (ra.get("status") == "LIMIT" and ra.get("ex") == "binance" and o.get("type") == "LIMIT" and o.get("side") == "BUY"
                       and o.get("price") == "10" and X["mtype"].get("AAAUSDT") == "ISOLATED" and X["lev"].get("AAAUSDT") == ra["lev"]
                       and 80 <= loss <= 100 and ra["lev"] <= 50)
# (3) the fill -> the stop (algo, the whole position) + the take (reduce-only limit)
o.update(status="FILLED", executedQty=o["quantity"], avgPrice="9.99"); X["pos"]["AAAUSDT"] = float(o["quantity"])
V.dlm_real_tick()
t = next(t for t in V._DLM["trades"] if t["symbol"] == "AAA_USDT"); rt = t["real"]
sl = X["algos"].get(int(rt.get("sl_id") or 0)) or {}; tp = X["orders"].get(int(rt.get("tp_id") or 0)) or {}
res["fill -> stop + take"] = (t["status"] == "OPEN" and abs(t["entry"] - 9.99) < 1e-9 and sl.get("type") == "STOP_MARKET" and sl.get("closePosition") == "true"
                              and sl.get("side") == "SELL" and abs(float(sl["triggerPrice"]) - 9.79) < 1e-9 and tp.get("type") == "LIMIT"
                              and tp.get("reduceOnly") == "true" and abs(float(tp["price"]) - 10.09) < 1e-9 and tp["quantity"] == o["quantity"]
                              and t["bs"] == 14400 and t["hold"] == 32 and t["fbar"] % 14400 == 0)
res["fill told in Telegram"] = any("AAA" in m and "⚡ Лимитки" in m and "исполнилась на Binance" in m and "оценка модели" in m and "риск" in m for m in TG)   # v0.99.705
# (4) the take fills -> WIN, the stop cancelled
tp.update(status="FILLED", executedQty=tp["quantity"]); X["pos"]["AAAUSDT"] = 0.0
V.dlm_real_tick()
res["take -> WIN"] = t["result"] == "WIN" and t["r"] > 0 and sl["algoStatus"] == "CANCELED"
# (5) a 1000-coin short: the prices x1000; the stop fires -> LOSS, the take cancelled
b = mk("PEPE_USDT", -1, 0.00001, 0.0000002); V._DLM["orders"].append(b)
V.dlm_real_place(b)
ob = X["orders"][int(b["real"]["id"])]
res["1000-coin scaled"] = ob["side"] == "SELL" and abs(float(ob["price"]) - 0.01) < 1e-12 and ob["newClientOrderId"].startswith("vpdlm")
ob.update(status="FILLED", executedQty=ob["quantity"], avgPrice="0.01"); X["pos"]["1000PEPEUSDT"] = -float(ob["quantity"])
V.dlm_real_tick()
tb2 = next(t for t in V._DLM["trades"] if t["symbol"] == "PEPE_USDT"); r2 = tb2["real"]
s2 = X["algos"][int(r2["sl_id"])]; t2 = X["orders"][int(r2["tp_id"])]
okp = s2["side"] == "BUY" and abs(float(s2["triggerPrice"]) - 0.0104) < 1e-9 and abs(float(t2["price"]) - 0.0098) < 1e-9
V.dlm_real_tick()   # the position seen once (a stop within the first minute of an unseen position waits that minute)
s2["algoStatus"] = "FINISHED"; X["pos"]["1000PEPEUSDT"] = 0.0
V.dlm_real_tick()
res["stop -> LOSS"] = okp and tb2["result"] == "LOSS" and t2["status"] == "CANCELED" and tb2["r"] < -0.9
# (6) the time exit: at the market, reduce-only
c_ = mk("BBB_USDT", 1, 5.0, 0.05); V._DLM["orders"].append(c_)
V.dlm_real_place(c_)
oc = X["orders"][int(c_["real"]["id"])]
oc.update(status="FILLED", executedQty=oc["quantity"], avgPrice="5"); X["pos"]["BBBUSDT"] = float(oc["quantity"])
V.dlm_real_tick()
tc = next(t for t in V._DLM["trades"] if t["symbol"] == "BBB_USDT"); tc["until"] = time.time() - 1; X["mark"] = {"BBBUSDT": 5.01}
V.dlm_real_tick()
mkt = [x for x in X["orders"].values() if x["type"] == "MARKET"]
res["time exit"] = (tc["result"] == "TIME_EXIT" and abs(tc["exit"] - 5.01) < 1e-9 and mkt and mkt[-1]["reduceOnly"] == "true" and mkt[-1]["side"] == "SELL"
                    and X["algos"][int(tc["real"]["sl_id"])]["algoStatus"] == "CANCELED" and X["orders"][int(tc["real"]["tp_id"])]["status"] == "CANCELED")
# (7) an unfilled limit after its 4 bars -> cancelled, EXPIRED
d = mk("AAA_USDT", -1, 11.0, 0.1); d["until"] = time.time() + 600; V._DLM["orders"].append(d)
V.dlm_real_place(d); d["until"] = time.time() - 1
V.dlm_real_tick()
res["expired"] = d["status"] == "EXPIRED" and X["orders"][int(d["real"]["id"])]["status"] == "CANCELED"
# (7b) v0.99.690 — the take at 2 ATR; the price goes 0.4 ATR against before +1 ATR -> the take order moved to 1 ATR
m0 = V._DLM["model"]
V._DLM["model"] = {"rule": m0["rule"], "streams": [{"name": "wick4h", "tf": "4h", "bar_sec": 14400, "take_atr": 1.0, "far_take_atr": 2.0, "pull_atr": 0.4,
                                                    "stop_atr": 2.0, "hold_bars": 32, "alive_bars": 4}]}
f = mk("AAA_USDT", 1, 10.0, 0.1); f["id"] += "f"; f["st"] = "wick4h"; V._DLM["orders"].append(f)
V.dlm_real_place(f); of = X["orders"][int(f["real"]["id"])]
of.update(status="FILLED", executedQty=of["quantity"], avgPrice="10"); X["pos"]["AAAUSDT"] = float(of["quantity"]); X["mark"] = {"AAAUSDT": 10.0}
KL = []
V.binance_klines = lambda sym, iv, a_, b_: [c for c in KL if a_ <= c["time"] <= b_] if sym == "AAA_USDT" and iv == "1m" else []
V.dlm_real_tick()
tf_ = next(t for t in V._DLM["trades"] if t["id"] == f["id"]); tp_a = X["orders"][int(tf_["real"]["tp_id"])]
far_ok = abs(float(tp_a["price"]) - 10.2) < 1e-9 and tf_["take"] == "far"
m_ = int(time.time()) // 60 * 60; tf_["t_in"] = m_ - 30; tf_["mw"] = 0
KL += [{"time": m_, "open": 10.0, "high": 10.01, "low": 9.95, "close": 9.97}]   # 0.5 ATR against, +1 ATR not reached
V.dlm_real_tick()
tp_b = X["orders"][int(tf_["real"]["tp_id"])]
res["take 2 ATR -> 1 ATR after a dip"] = (far_ok and tf_["take"] == "near" and tp_a["status"] == "CANCELED" and abs(float(tp_b["price"]) - 10.1) < 1e-9
                                          and tp_b["reduceOnly"] == "true" and tp_b["status"] == "NEW" and abs(tf_["tp"] - 10.1) < 1e-9)
tp_b.update(status="FILLED", executedQty=tp_b["quantity"]); X["pos"]["AAAUSDT"] = 0.0
V.dlm_real_tick()
res["take 2 ATR -> 1 ATR after a dip"] &= tf_["result"] == "WIN" and abs(tf_["exit"] - 10.1) < 1e-9
V._DLM["model"] = m0
# (7b2) v0.99.692 — a close1h stream on Binance: the STOP_MARKET at the emergency 3 ATR, the take 1.1 ATR, the risk % at
# the 2 ATR stop; a 1h close beyond the stop -> out at the market, LOSS (v0.99.694: the 4h close of a 4h stream)
V._DLM["model"] = {"rule": m0["rule"], "streams": [{"name": "wick4h", "tf": "4h", "bar_sec": 14400, "take_atr": 1.1, "stop_atr": 2.0, "hard_stop_atr": 3.0,
                                                    "stop_mode": "close1h", "close_h": 4, "hold_bars": 32, "alive_bars": 4}]}
j = mk("AAA_USDT", 1, 10.0, 0.1); j["id"] += "j"; j["st"] = "wick4h"; V._DLM["orders"].append(j)
V.dlm_real_place(j); oj = X["orders"][int(j["real"]["id"])]
oj.update(status="FILLED", executedQty=oj["quantity"], avgPrice="10"); X["pos"]["AAAUSDT"] = float(oj["quantity"]); X["mark"] = {"AAAUSDT": 9.9}
H1J = []
V._dlm_1h = lambda sym, start, now: [c for c in H1J if c["time"] >= start and c["time"] + 3600 <= now] if sym == "AAA_USDT" else []
V.dlm_real_tick()
tj = next(t for t in V._DLM["trades"] if t["id"] == j["id"]); rj = tj["real"]
slj = X["algos"].get(int(rj.get("sl_id") or 0)) or {}; tpj = X["orders"].get(int(rj.get("tp_id") or 0)) or {}
loss_at_stop = float(oj["quantity"]) * 0.2   # the 2 ATR stop
ok_j = (abs(float(slj.get("triggerPrice", 0)) - 9.7) < 1e-9 and abs(float(tpj.get("price", 0)) - 10.11) < 1e-9 and j["real"]["risk"] == V.dlm_risk()
        and 0.8 * V.dlm_risk() * 10 <= loss_at_stop <= 1.01 * V.dlm_risk() * 10)   # the risk % of the $1000 at the 2 ATR stop
h0 = int(time.time()) // 14400 * 14400 - 3 * 3600; tj["t1h"] = h0; tj["cs_bar"] = 0   # v0.99.694 — h0+2h ends a 4h candle
H1J += [{"time": h0, "open": 10.0, "high": 10.02, "low": 9.75, "close": 9.85},   # a wick to 9.75 (below the stop 9.8), closed back
        {"time": h0 + 3600, "open": 9.85, "high": 9.86, "low": 9.74, "close": 9.78}]   # an hour closed beyond — not the 4h close
V.dlm_real_tick(); ok_j = ok_j and tj["status"] == "OPEN" and tj.get("ch") == 4
H1J += [{"time": h0 + 7200, "open": 9.78, "high": 9.8, "low": 9.72, "close": 9.76}]; tj["cs_bar"] = h0 - 30   # the 4h candle closed beyond
V.dlm_real_tick()
mk_ = [x for x in X["orders"].values() if x["type"] == "MARKET"]
res["close stop: emergency stop 3 ATR, take 1.1, out at the 4h close (not a wick / a 1h close)"] = (ok_j and tj["status"] == "CLOSED" and tj["result"] == "LOSS" and tj.get("close_stop")
                                                                       and mk_ and mk_[-1]["side"] == "SELL" and slj.get("algoStatus") == "CANCELED")
V._DLM["model"] = m0
# (7c) v0.99.691 — a waiting order goes on Binance when the price comes within 0.3 ATR (the tickers), not at the scan
g = mk("BBB_USDT", 1, 5.0, 0.05); g["id"] += "g"; V._DLM["orders"].append(g)
X["px"] = {"BBBUSDT": 5.5}   # 10 ATR away: waits
V.dlm_real_tick(); far_wait = g.get("real") is None
X["px"] = {"BBBUSDT": 5.01}   # 0.2 ATR: armed
V.dlm_real_tick(); og = X["orders"].get(int((g.get("real") or {}).get("id") or 0)) or {}
res["armed on Binance as the price comes"] = far_wait and og.get("type") == "LIMIT" and og.get("price") == "5" and g["real"].get("ex") == "binance"
X["px"] = {"BBBUSDT": 5.2}   # 4 ATR away again: off, waiting
V.dlm_real_tick()
res["armed on Binance as the price comes"] &= og.get("status") == "CANCELED" and g.get("real") is None and g["status"] == "OPEN"
# (8) the free margin: the risk scaled down; (9) below the minimum notional -> skipped
V.apply_settings({"risk_pct_dlm2": 50}); X["free"] = 5.0
e = mk("AAA_USDT", 1, 10.0, 0.1); e["id"] += "e"; V._DLM["orders"].append(e)
V.dlm_real_place(e)
res["risk capped 10%, free margin -> risk scaled"] = V.dlm_risk() == 10 and e["real"]["status"] == "LIMIT" and e["real"]["risk"] < 10
X["orders"][int(e["real"]["id"])]["status"] = "CANCELED"; e["status"] = "CANCELLED"
X.update(wallet=1.0, free=1.0)
f = mk("BBB_USDT", 1, 5.0, 0.05); f["id"] += "f"; V._DLM["orders"].append(f)
V.dlm_real_place(f)
res["tiny account -> skipped"] = f["real"]["status"] == "SKIPPED"
X.update(wallet=1000.0, free=1000.0)
# (10) no Algo API -> the old STOP_MARKET order; (11) a hedge-mode account that cannot switch -> positionSide on every order
X["algo_api"] = False; X["dual"] = True; X["dual_lock"] = True; V._BNF["dual"] = None
g = mk("BBB_USDT", -1, 5.0, 0.05); g["id"] += "g"; V._DLM["orders"].append(g)
V.dlm_real_place(g)
og = X["orders"][int(g["real"]["id"])]
og.update(status="FILLED", executedQty=og["quantity"], avgPrice="5"); X["pos"]["BBBUSDT"] = -float(og["quantity"])
V.dlm_real_tick()
tg = next(t for t in V._DLM["trades"] if t["id"] == g["id"]); rg = tg["real"]
st = X["orders"].get(int(rg.get("sl_id") or 0)) or {}; tk = X["orders"].get(int(rg.get("tp_id") or 0)) or {}
res["old endpoint + hedge mode"] = (og.get("positionSide") == "SHORT" and "reduceOnly" not in og and rg.get("sl_kind") == "order" and st.get("type") == "STOP_MARKET"
                                    and st.get("positionSide") == "SHORT" and tk.get("positionSide") == "SHORT" and "reduceOnly" not in tk)
X["pos"]["BBBUSDT"] = 0.0; tk.update(status="FILLED", executedQty=tk["quantity"]); V.dlm_real_tick()
X.update(algo_api=True, dual=False, dual_lock=False); V._BNF["dual"] = None
# (12) at most DLM_MAX_POS positions (v0.99.687): one open real trade and a cap of 1 -> a new limit is not placed
V._DLM["orders"] = []; V._DLM["trades"] = [t for t in V._DLM["trades"] if t["status"] != "OPEN"]
V._DLM["trades"].append({"id": "held", "symbol": "ZZZ_USDT", "side": 1, "status": "OPEN", "real": {"ex": "binance", "bsym": "ZZZUSDT"}})
cap0 = V.DLM_MAX_POS; V.DLM_MAX_POS = 1
h = mk("AAA_USDT", 1, 10.0, 0.1); h["id"] += "h"; V._DLM["orders"].append(h)
V.dlm_real_place(h)
res["position cap"] = not h.get("real")
V.DLM_MAX_POS = cap0; V._DLM["trades"] = [t for t in V._DLM["trades"] if t["id"] != "held"]
# (13) the UI
# v0.99.713 — a new futures account (Binance -4300: no more than 20x for 30 days): the cap learnt, the order made again
X["lev_cap"] = 20; X["algo_api"] = True; X["dual"] = False; X["dual_lock"] = False; V._BNF["dual"] = None; X["pos"].clear(); V._BNF.pop("lev_cap", None)
V._DLM.update({"orders": [], "trades": []}); w0 = (X["wallet"], X["free"]); X["wallet"] = X["free"] = 100.0   # a small notional: the 50x bracket
q4 = mk("AAA_USDT", 1, 10.0, 0.02); V._DLM["orders"].append(q4); V.dlm_real_place(q4)
res["new account: leverage capped at 20x, the order made"] = (q4["real"] or {}).get("status") == "LIMIT" and V._BNF.get("lev_cap") == 20 and X["lev"].get("AAAUSDT", 99) <= 20
X["lev_cap"] = None; V._BNF.pop("lev_cap", None); X["wallet"], X["free"] = w0
for i_ in [int(q4["real"].get("id") or 0)] + [int((q4["real"].get(k) or [0, 0])[1]) for k in ("pre_sl", "pre_tp")]:   # its limit gone
    X["orders"].pop(i_, None); X["algos"].pop(i_, None)
# v0.99.715 — the user ("сделка закрылась тейком, но её нигде нет", "особенно параллельный поток"): (a) the coin's limit of
# the other stream on the exchange, this one nearer the price -> swapped; (b) farther -> waits with the reason; (c) the coin
# held by a P/R / SMC / EMA position -> waits (not skipped for good) and says by whom; (d) a virtual trade gives that reason
X["algo_api"] = True; X["dual"] = False; X["dual_lock"] = False; V._BNF["dual"] = None; X["pos"].clear()
V._DLM.update({"orders": [], "trades": []}); V._BNO["pos"].clear()
A4 = mk("EEE_USDT", 1, 10.0, 0.1); A4["id"] += "w4"; V._DLM["orders"].append(A4)
X["px"] = {"EEEUSDT": 10.09}; V.dlm_real_tick(); a_id = (A4.get("real") or {}).get("id")   # the 4h one armed (0.9 ATR away)
B2 = mk("EEE_USDT", 1, 9.995, 0.1); B2.update(id=B2["id"] + "c2", st="close2h", bs=7200); V._DLM["orders"].append(B2)
V.dlm_real_tick()   # the 2h one 0.95 ATR away, farther than the 4h one: waits, says why
far_hold = B2.get("real") is None and "другого потока" in (B2.get("hold") or "") and (A4.get("real") or {}).get("id") == a_id
B3 = mk("EEE_USDT", 1, 10.06, 0.1); B3.update(id=B3["id"] + "c3", st="close2h", bs=7200); V._DLM["orders"].append(B3)
V.dlm_real_tick()   # another 2h one 0.3 ATR away — nearer than the 4h one by more than 0.25 ATR: swapped
sw = (X["orders"][int(a_id)]["status"] == "CANCELED" and A4.get("real") is None and "снята с биржи" in (A4.get("hold") or "")
      and (B3.get("real") or {}).get("status") == "LIMIT" and B2.get("real") is None)
V.dlm_real_tick(); sw = sw and A4.get("real") is None and (B3.get("real") or {}).get("status") == "LIMIT"   # no swap back
res["parallel stream: the nearer limit on the exchange, the other waits with the reason"] = bool(a_id) and far_hold and sw
print("   swap:", bool(a_id), far_hold, sw, A4.get("hold"), "|", B2.get("hold"))
for o_ in (A4, B2, B3):
    if (o_.get("real") or {}).get("id"): V._dlm_cancel_back(o_)
V._DLM["orders"] = []
C3 = mk("FFF_USDT", -1, 7.0, 0.07); V._DLM["orders"].append(C3); X["pos"]["FFFUSDT"] = 3.0
V._BNO["pos"]["FFF_USDT"] = {"mode": "smc", "bsym": "FFFUSDT", "side": 1}
V.dlm_real_place(C3)
held_ok = C3.get("real") is None and "SMC" in (C3.get("hold") or "")
why = V._dlm_why_virtual(C3, {"t1h": int(time.time())})
res["coin held by SMC: waits, the reason in the virtual trade"] = held_ok and "SMC" in why
X["pos"].pop("FFFUSDT", None); V._BNO["pos"].clear(); V._DLM["orders"] = []
# v0.99.716 — "пока бот пересчитывал свечи" only for an order of the catch-up itself
cu0 = V._DLM.get("catchup"); V._DLM["catchup"] = {"t": int(time.time()) - 60, "run": True, "done": 1, "of": 8}
o_ = {"symbol": "GGG_USDT", "side": 1, "lv": 1.0, "t0": int(time.time()) - 3600, "real": None, "hold": "заняты все 20 мест: сделок ⚡ на бирже 12, лимиток 8"}
w1 = V._dlm_why_virtual(o_, {"t1h": int(time.time())}); w2 = V._dlm_why_virtual(dict(o_, from_cu=True), {"t1h": int(time.time())})
res["the catch-up reason only for the catch-up's orders"] = "20 мест" in w1 and "пересчитывал" in w2
V._DLM["catchup"] = cu0
# v0.99.708 — (a) the limit goes with its stop + take (closePosition triggers) and a GTD; (b) "another phone": the state lost ->
# the bot takes over its limit (with its triggers), a ⚡ position (stop + take limit) and an SMC-like one (stop + take
# triggers: take / stop = 1.5), nothing placed or cancelled on the exchange
X["algo_api"] = True; X["dual"] = False; X["dual_lock"] = False; V._BNF["dual"] = None; X["pos"].clear()
V._DLM.update({"orders": [], "trades": []}); V._BNO["pos"].clear()
now = time.time(); tb = int(now // 14400 * 14400)
g = mk("AAA_USDT", 1, 10.0, 0.1); V._DLM["orders"].append(g); V.dlm_real_place(g)
rg = g["real"]; lo = X["orders"].get(int(rg.get("id") or 0)) or {}
psl = X["algos"].get(int((rg.get("pre_sl") or [0, 0])[1])) or {}; ptp = X["algos"].get(int((rg.get("pre_tp") or [0, 0])[1])) or {}
res["limit with its stop + take, GTD"] = (lo.get("timeInForce") == "GTD" and int(lo.get("goodTillDate", 0)) >= (now + 600) * 1000
                                          and psl.get("type") == "STOP_MARKET" and psl.get("closePosition") == "true" and psl.get("triggerPrice") == "9.8"
                                          and ptp.get("type") == "TAKE_PROFIT_MARKET" and ptp.get("triggerPrice") == "10.1")
h = mk("BBB_USDT", -1, 20.0, 0.2); V._DLM["orders"].append(h); V.dlm_real_place(h)
ho = X["orders"][int(h["real"]["id"])]; ho.update(status="FILLED", executedQty=ho["quantity"], avgPrice="20"); X["pos"]["BBBUSDT"] = -float(ho["quantity"]); X.setdefault("entry", {})["BBBUSDT"] = 20.0
V.dlm_real_tick()
tB = next(t for t in V._DLM["trades"] if t["symbol"] == "BBB_USDT"); sl0, tp0 = tB["real"].get("sl_id"), tB["real"].get("tp_id")
X["pos"]["CCCUSDT"] = 10.0; X["entry"]["CCCUSDT"] = 5.0
for kind, trg in (("STOP_MARKET", "4.8"), ("TAKE_PROFIT_MARKET", "5.3")):
    i = oid(); X["algos"][i] = {"symbol": "CCCUSDT", "side": "SELL", "type": kind, "triggerPrice": trg, "closePosition": "true", "algoId": i, "algoStatus": "NEW"}
V._DLM.update({"orders": [], "trades": []}); V._BNO["pos"].clear()   # the new phone: no state
_atr = V._dlm_atr_at; V._dlm_atr_at = lambda sym, t, bs=14400: 0.1
n0 = len(X["calls"]); got = V.dlm_bn_adopt()
moves = [c for c in X["calls"][n0:] if c[0] in ("POST", "DELETE") and c[1] in ("/fapi/v1/order", "/fapi/v1/algoOrder")]
oA = next((o for o in V._DLM["orders"] if (o.get("real") or {}).get("id") == rg["id"]), None)
tB2 = next((t for t in V._DLM["trades"] if t["symbol"] == "BBB_USDT" and t["status"] == "OPEN"), None)
cc = V._BNO["pos"].get("CCC_USDT") or {}
res["new phone: takes over, cancels nothing"] = (not moves and oA is not None and oA["side"] == 1 and abs(oA["lv"] - 10.0) < 1e-9 and (oA["real"].get("pre_sl") or [0, 0])[1] == rg["pre_sl"][1]
                                                 and tB2 is not None and tB2["side"] == -1 and tB2["real"].get("sl_id") == sl0 and tB2["real"].get("tp_id") == tp0
                                                 and abs(tB2["entry"] - 20.0) < 1e-9 and cc.get("mode") == "smc" and cc.get("sl_id") and cc.get("tp_id") and len(got) == 3)
V.dlm_real_tick()   # the next tick: the adopted ones managed, nothing new placed for them
res["adopted managed on the next tick"] = tB2["status"] == "OPEN" and tB2["real"].get("sl_id") == sl0 and oA["status"] == "OPEN"
# v0.99.714 — a stop / take with no position, no entry order and no record (a limit's GTD ended while the bot was off, the
# phone changed) -> cancelled; the ones of the live limit (AAA) and of the positions (BBB, CCC) kept
oD = oid(); X["algos"][oD] = {"symbol": "DDDUSDT", "side": "SELL", "type": "STOP_MARKET", "triggerPrice": "1.0", "closePosition": "true", "algoId": oD, "algoStatus": "NEW"}
keep = [i for i, a_ in X["algos"].items() if a_["algoStatus"] == "NEW" and a_["symbol"] in ("AAAUSDT", "BBBUSDT", "CCCUSDT")]
got2 = V.dlm_bn_adopt()
res["orphan stop cancelled, the others kept"] = (X["algos"][oD]["algoStatus"] != "NEW" and all(X["algos"][i]["algoStatus"] == "NEW" for i in keep)
                                                 and any("DDDUSDT" in l_ for l_ in got2))
V._dlm_atr_at = _atr
print("   adopt:", got, got2)
html = V.app.test_client().get("/").get_data(as_text=True)
st = V.app.test_client().get("/api/dlm/status").get_json()
res["ui"] = "setDlmBinance" in html and "bnSaveKeys" in html and st["binance"] is True and st["bn_keys"] is True and st["bn_check"]["ok"]
V.app.test_client().post("/api/binance/credentials", json={"clear": True})
res["keys cleared"] = not os.path.exists(V.BINANCE_CREDENTIALS_FILE) and not V.BINANCE_API_KEY
print(" · ".join(f"{k} {v}" for k, v in res.items()))
ok = all(bool(v) for v in res.values())
print("ALL OK" if ok else "FAILED"); sys.exit(0 if ok else 1)
