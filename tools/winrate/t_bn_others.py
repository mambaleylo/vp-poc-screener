"""v0.99.698 — P/R, SMC, EMA on Binance (the ⚡ account) against the fake Binance of t_dlm_binance.py: the market entry, the
isolated margin and the leverage, the size by the risk (the module's field, empty = 2%) at the stop, the STOP_MARKET and the
TAKE_PROFIT_MARKET on the exchange, one position a coin (a position / an armed ⚡ limit -> skipped), EMA's partial take
(reduce-only, the stop to the entry), the time exit at the market, the cleanup after the exchange's stop / take, a 1000-coin
scaled, the dry run, the switch off -> Gate, the setting"""

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
        if X["mtype"].get(p["symbol"]) == p["marginType"]:
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
V._BNC[("AAA_USDT", "4h")] = {"bsym": "AAAUSDT", "scl": 1.0, "cols": [[]] * 6}
V._BNC[("PEPE_USDT", "2h")] = {"bsym": "1000PEPEUSDT", "scl": 1000.0, "cols": [[]] * 6}
V._BNC[("BBB_USDT", "4h")] = {"bsym": "BBBUSDT", "scl": 1.0, "cols": [[]] * 6}
V._DLM["model"] = {"rule": {"stop_atr": 2.0, "take_atr": 1.0, "hold_bars": 32, "alive_bars": 4, "bar_sec": 14400}}   # v0.99.687 — the 4h rule
res = {}


V.BINANCE_API_KEY, V.BINANCE_API_SECRET = KEY, SEC
V.BNO_FILE = os.path.join(tempfile.mkdtemp(), "bno.json")
V.AUTOTRADE_DRY_RUN = False
for m_ in ("prv", "smc", "emw"): V.MODULE_RISK_PCT[m_] = None   # empty: the per-module defaults (v0.99.727: P/R 3, SMC 2.5, EMA 2)
V.apply_settings({"bn_others": True})
res["setting on"] = V.BN_OTHERS is True and V.get_settings().get("bn_others") is True if hasattr(V, "get_settings") else V.BN_OTHERS is True
gate = []
V._execute_autotrade_impl = lambda *a, **k: (gate.append(a[0]), {"status": "OPENED", "detail": "gate"})[1]

# (1) SMC long AAA: entry 10, stop 9.5 (5%), take 11.5 -> SMC's default 2.5% of $1000 = $25 at the stop -> $500, 50 coins (v0.99.727; was 1.5%)
X["calls"].clear()
r1 = V.execute_autotrade("smc", "AAA_USDT", "LONG", 10.0, 9.5, 11.5, risk_pct_override=0.25)
mk = [c for c in X["calls"] if c[1] == "/fapi/v1/order" and c[2].get("type") == "MARKET"]
algos = [a for a in X["algos"].values() if a["symbol"] == "AAAUSDT"]
st = next((a for a in algos if a["type"] == "STOP_MARKET"), {}); tk = next((a for a in algos if a["type"] == "TAKE_PROFIT_MARKET"), {})
q = float(mk[0][2]["quantity"]) if mk else 0
res["smc opened on Binance, its 2.5% at the stop"] = (r1["status"] == "OPENED" and not gate and len(mk) == 1 and mk[0][2]["side"] == "BUY"
                                               and 0.9 * 25 <= q * 0.5 <= 1.001 * 25 and X["mtype"].get("AAAUSDT") == "CROSSED" and X["lev"].get("AAAUSDT", 0) == 50)   # v0.99.717 — cross; v0.99.744: the coin's bracket 50x (was 10x)
# v0.99.744 — the cross leverage is the coin's bracket at the position's size, within the account's cap
tb_ = {"AAAUSDT": [(5000.0, 0.01, 50), (25000.0, 0.025, 20)]}
m1, l1, _ = V.bn_size("LONG", 10.0, 9.5, 50, 0.01, 1000.0, 2.5, "AAAUSDT", tb_, "CROSSED")
m2, l2, _ = V.bn_size("LONG", 10.0, 9.5, 50, 0.01, 20000.0, 2.5, "AAAUSDT", tb_, "CROSSED")    # $500 at the stop -> $10000 notional
m3, l3, _ = V.bn_size("LONG", 10.0, 9.5, 20, 0.01, 1000.0, 2.5, "AAAUSDT", tb_, "CROSSED")     # the account's cap 20x
print(f"   cross lev: small {l1}x margin {m1:.1f}$ · big {l2}x margin {m2:.1f}$ · account cap {l3}x")
_cl = V.BN_CROSS_LEV; V.BN_CROSS_LEV = 10; m0, l0, _ = V.bn_size("LONG", 10.0, 9.5, 50, 0.01, 1000.0, 2.5, "AAAUSDT", tb_, "CROSSED"); V.BN_CROSS_LEV = _cl
print(f"   the same position at 10x: margin {m0:.1f}$ (now {m1:.1f}$), notional {m0 * l0:.0f}$ = {m1 * l1:.0f}$")
res["cross: the bracket's leverage, the account's cap"] = (l1 == 50 and l0 == 10 and abs(m1 * l1 - m0 * l0) < 1e-6 and m1 < m0 / 4.9   # the same size (risk), 1/5 of the margin
                                                           and l2 == 20 and abs(m2 * l2 - 20 * m1 * l1) < 1 and l3 == 20)
res["stop + take on the exchange"] = (st.get("triggerPrice") == "9.5" and st.get("closePosition") == "true" and st.get("side") == "SELL"
                                     and tk.get("triggerPrice") == "11.5" and tk.get("closePosition") == "true")
X["pos"]["AAAUSDT"] = q
# (2) the same coin again (P/R) -> skipped: a position on it
r2 = V.execute_autotrade("prv", "AAA_USDT", "SHORT", 10.0, 10.6, 9.0)
res["one position a coin"] = r2["status"] == "SKIPPED" and "позиция" in r2["detail"]
# (3) an armed ⚡ limit on BBB -> EMA on BBB skipped
V._DLM["orders"] = [{"id": "o1", "symbol": "BBB_USDT", "side": 1, "lv": 4.0, "status": "OPEN", "real": {"id": "77", "ex": "binance"}}]
r3 = V.execute_autotrade("emw", "BBB_USDT", "LONG", 5.0, 4.8, 5.4)
res["an armed ⚡ limit blocks the coin"] = r3["status"] == "SKIPPED" and "лимитка" in r3["detail"]
V._DLM["orders"] = []
# (4) EMA long BBB: its 2% at a 4% stop -> $500, 100 coins; the partial take: half off reduce-only, the stop to the entry
r4 = V.execute_autotrade("emw", "BBB_USDT", "LONG", 5.0, 4.8, 5.4)
qb = float(V._BNO["pos"]["BBB_USDT"]["qty"]); X["pos"]["BBBUSDT"] = qb
old_sl = V._BNO["pos"]["BBB_USDT"]["sl_id"]
X["calls"].clear()
note = V.part_take_on_exchange("emw", {"symbol": "BBB_USDT", "side": 1, "direction": "LONG", "px": 5.0, "entry": 5.0, "sl": 4.8}, 0.5)
pm = [c for c in X["calls"] if c[1] == "/fapi/v1/order" and c[2].get("type") == "MARKET"]
new_sl = V._BNO["pos"]["BBB_USDT"]["sl_id"]
res["EMA partial: half off, stop to the entry"] = (r4["status"] == "OPENED" and pm and pm[0][2]["side"] == "SELL" and pm[0][2].get("reduceOnly") == "true"
                                                   and abs(float(pm[0][2]["quantity"]) - qb / 2) <= 1 and X["algos"][int(old_sl)]["algoStatus"] == "CANCELED"
                                                   and X["algos"][int(new_sl)]["triggerPrice"] == "5" and "Binance" in note)
X["pos"]["BBBUSDT"] = qb - float(pm[0][2]["quantity"]) if pm else qb
# (5) the time exit: the triggers off, the rest at the market, the record gone
X["calls"].clear(); rest = X["pos"]["BBBUSDT"]
c5 = V.close_position_for_mode("emw", "BBB_USDT", "LONG")
cm = [c for c in X["calls"] if c[1] == "/fapi/v1/order" and c[2].get("type") == "MARKET"]
left = [a for a in X["algos"].values() if a["symbol"] == "BBBUSDT" and a["algoStatus"] == "NEW"]
res["time exit at the market"] = (c5.get("ok") and cm and cm[0][2]["side"] == "SELL" and float(cm[0][2]["quantity"]) == rest
                                  and not left and "BBB_USDT" not in V._BNO["pos"])
# v0.99.719 — SMC's break-even: (a) the walk — +2R reached, then back at the entry -> out at the entry; (b) a real SMC
# position on Binance: the price at +2R -> its exchange stop at the entry, nothing closed
cs_ = [{"time": 0, "open": 10.0, "high": 10.2, "low": 9.9, "close": 10.1}, {"time": 3600, "open": 10.1, "high": 11.05, "low": 10.1, "close": 10.9},
       {"time": 7200, "open": 10.9, "high": 10.95, "low": 9.95, "close": 10.0}]
w_be = V._cs_walk(cs_, 1, 10.0, 9.5, 11.5, 96, 4, 2.0, V.SMC_BE_R); w_no = V._cs_walk(cs_, 1, 10.0, 9.5, 11.5, 96, 4, 2.0, 0.0)
X["calls"].clear(); hb = int(time.time()) // 3600 * 3600 - 3 * 3600   # the touch's hour; +2R inside the hour after it
CND = {"AAA_USDT": [{"time": hb + 3600, "open": 10.1, "high": 10.9, "low": 10.0, "close": 10.8}]}   # first: not yet +2R (11)
_gcr = V.get_candles_range; V.get_candles_range = lambda sym, tf, a_, b_: [c for c in CND.get(sym, []) if a_ <= c["time"] <= b_]
V._SMC["trades"] = [{"id": "s1", "symbol": "AAA_USDT", "side": 1, "direction": "LONG", "entry": 10.0, "px": 10.0, "sl": 9.5, "tp": 11.5, "hour": hb,
                     "status": "OPEN", "real": True, "rv": V.SMC_MODEL_VER}]
V.AUTOTRADE_ENABLED_SMC = True; V.smc_save = lambda: None
V.smc_be_tick(); not_yet = not V._SMC["trades"][0].get("be_done") and not [c for c in X["calls"] if c[1] == "/fapi/v1/algoOrder"]
CND["AAA_USDT"].append({"time": hb + 7200, "open": 10.8, "high": 11.05, "low": 10.7, "close": 10.95})   # a closed hour reached +2R
V._SMC["trades"][0].pop("be_chk", None); V.smc_be_tick(); V.get_candles_range = _gcr
newst = [a_ for a_ in X["algos"].values() if a_["symbol"] == "AAAUSDT" and a_["type"] == "STOP_MARKET" and a_["algoStatus"] == "NEW"]
mk_be = [c for c in X["calls"] if c[1] == "/fapi/v1/order" and c[2].get("type") == "MARKET"]
res["SMC break-even after +2R (walk + exchange stop)"] = (not_yet and w_be and w_be[0] == "BREAKEVEN" and abs(w_be[1] - 10.0) < 1e-9 and w_no is None
                                                         and V._SMC["trades"][0].get("be_done") and len(newst) == 1 and newst[0]["triggerPrice"] == "10"
                                                         and not mk_be and V._BNO["pos"]["AAA_USDT"].get("sl_px") == 10.0)
print("   be:", w_be, w_no, [a_["triggerPrice"] for a_ in newst], len(mk_be))
V._SMC["trades"] = []
# (6) the exchange's stop closed AAA: the take off, the record dropped
X["pos"]["AAAUSDT"] = 0.0; V._BNO["pos"]["AAA_USDT"]["t"] -= 120
V.bno_tick()
res["cleanup after the stop"] = "AAA_USDT" not in V._BNO["pos"] and all(a["algoStatus"] != "NEW" for a in X["algos"].values() if a["symbol"] == "AAAUSDT")
# (7) a 1000-coin: Gate PEPE 0.00001 -> Binance 1000PEPE 0.01 (the stop / take x1000)
V.MODULE_RISK_PCT["smc"] = 1.0
r7 = V.execute_autotrade("smc", "PEPE_USDT", "SHORT", 0.00001, 0.0000105, 0.0000092)
pa = [a for a in X["algos"].values() if a["symbol"] == "1000PEPEUSDT"]
res["1000-coin scaled, own risk field"] = (r7["status"] == "OPENED" and {a["type"]: a["triggerPrice"] for a in pa} == {"STOP_MARKET": "0.0105", "TAKE_PROFIT_MARKET": "0.0092"}
                                           and V._BNO["pos"]["PEPE_USDT"]["risk"] == 1.0)
# (8) dry run; (9) the switch off -> Gate
V.AUTOTRADE_DRY_RUN = True; r8 = V.execute_autotrade("prv", "CCC_USDT", "LONG", 1.0, 0.95, 1.1); V.AUTOTRADE_DRY_RUN = False
V.apply_settings({"bn_others": False}); r9 = V.execute_autotrade("smc", "CCC_USDT", "LONG", 1.0, 0.95, 1.1)
res["dry run / off -> Gate"] = r8["status"] == "DRY_RUN" and r9["detail"] == "gate" and gate == ["smc"]
# (10) the setting row in the page
html = V.app.test_client().get("/").get_data(as_text=True)
res["setting in the page"] = 'id="setBnOthers"' in html and "bn_others: document.getElementById('setBnOthers')" in html
# (11) v0.99.700 — the header's yearly expectation: the bundle when on, ⚡ alone when off
c_ = V.app.test_client(); V.apply_settings({"bn_others": True}); e1 = c_.get("/api/boot").get_json()["expect"]
V.apply_settings({"bn_others": False}); e0 = c_.get("/api/boot").get_json()["expect"]
res["header expectation (bundle / ⚡)"] = e1["kind"] == "bundle" and e0["kind"] == "dlm" and e1["p10"] < e1["p50"] < e1["p90"] and 'id="hdrExpect"' in html
print(" · ".join(f"{k} {v}" for k, v in res.items()))
ok = all(res.values())
print("ALL OK" if ok else "FAILED"); sys.exit(0 if ok else 1)
