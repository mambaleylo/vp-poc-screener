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
INFO = {"AAAUSDT": (0.001, 0.1, 0.1, 5.0), "1000PEPEUSDT": (0.0000001, 1.0, 1.0, 5.0), "BBBUSDT": (0.01, 1.0, 1.0, 5.0)}


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
        return R(200, [{"symbol": s, "positionAmt": str(a), "entryPrice": "1", "markPrice": str(X.get("mark", {}).get(s, 1)), "positionSide": "BOTH"}
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
V.send_telegram = lambda *a, **k: None
V.log_error = lambda m: print("   log:", m) if "binance algo" not in m and "binance one-way" not in m else None
V._BNC[("AAA_USDT", "15m")] = {"bsym": "AAAUSDT", "scl": 1.0, "cols": [[]] * 6}
V._BNC[("PEPE_USDT", "15m")] = {"bsym": "1000PEPEUSDT", "scl": 1000.0, "cols": [[]] * 6}
V._BNC[("BBB_USDT", "15m")] = {"bsym": "BBBUSDT", "scl": 1.0, "cols": [[]] * 6}
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
html = V.app.test_client().get("/").get_data(as_text=True)
st = V.app.test_client().get("/api/dlm/status").get_json()
res["ui"] = "setDlmBinance" in html and "bnSaveKeys" in html and st["binance"] is True and st["bn_keys"] is True and st["bn_check"]["ok"]
V.app.test_client().post("/api/binance/credentials", json={"clear": True})
res["keys cleared"] = not os.path.exists(V.BINANCE_CREDENTIALS_FILE) and not V.BINANCE_API_KEY
print(" · ".join(f"{k} {v}" for k, v in res.items()))
ok = all(bool(v) for v in res.values())
print("ALL OK" if ok else "FAILED"); sys.exit(0 if ok else 1)
