"""v0.99.787 — the missed ⚡ fills (TURBO / HOME, 9 Nov): (1) Binance answers -2013 "Order does not exist" for the limit — the
order found in the coin's order history (allOrders) and its fill taken as a ⚡ trade with its stop and take; (2) the order
unknown both ways after a cancel attempt -> nothing decided (the order stays, no "touched but not filled"), checked next
tick; (3) -4509 (Binance takes no stop before the position): asked once, then the limits go without, one note in the log
(a warning, not an error). Binance is a stub: no real order anywhere"""
import time, tempfile, os
from common import V
ok = True
def chk(nm, c):
    global ok
    print(("OK  " if c else "FAIL") + " " + nm); ok &= bool(c)
d = tempfile.mkdtemp(prefix="vpf787_"); V.DLM_STATE_FILE = os.path.join(d, "dlm.json")
sent = []; V.send_telegram = lambda t, category=None: sent.append(t)
logs = []; V.log_error = lambda m: logs.append(m)
B = {"order_err": True, "hist": "FILLED", "pos": {}}
placed = []; posts = []
def req(method, path, params=None):
    if path == "/fapi/v1/order" and method == "GET":
        if B["order_err"]:
            raise V.BinanceError(-2013, "Order does not exist.")
        return {"orderId": params["orderId"], "status": "NEW", "executedQty": "0"}
    if path == "/fapi/v1/allOrders":
        if B["hist"] is None:
            return []
        return [{"orderId": 8381445796, "status": B["hist"], "executedQty": "100000" if B["hist"] == "FILLED" else "0", "avgPrice": "0.0006964"}]
    if path == "/fapi/v1/order" and method == "DELETE":
        raise V.BinanceError(-2011, "Unknown order sent.")
    if method == "POST" and path == "/fapi/v1/order":
        posts.append(params); return {"orderId": 77}
    return {}
V.bnf_req = req
V.bnf_place_cond = lambda bsym, s, kind, px, dual: placed.append((bsym, kind, float(px))) or ("algo", f"a{len(placed)}")
V.bnf_positions = lambda: dict(B["pos"])
V._dlm_bn_fills = lambda now: False
def mk():
    now = time.time()
    return {"id": "dlm_TURBO_USDT_1_1794117600_wick4h_o2", "symbol": "TURBO_USDT", "side": 1, "lv": 0.0006964260041181499, "atr": 1.61e-5, "score": 1.0,
            "t0": int(now // 14400 * 14400) - 14400, "bs": 14400, "st": "wick4h", "until": now + 3600, "status": "OPEN",
            "real": {"status": "LIMIT", "ex": "binance", "id": "8381445796", "bsym": "TURBOUSDT", "scl": 1.0, "price": 0.0006964, "lev": 20,
                     "dual": False, "tick": 1e-7, "step": 1.0, "tif": "GTD"}}
# (1) -2013 on the order, found in the history as FILLED
o = mk(); B["pos"] = {"TURBOUSDT": [{"amt": 100000.0, "entry": 0.0006964, "mark": 0.00069, "pside": "BOTH"}]}
with V._dlm_lock:
    V._DLM["orders"] = [o]; V._DLM["trades"] = []
V.dlm_bn_tick([o], [])
t = next((x for x in V._DLM["trades"] if x["symbol"] == "TURBO_USDT"), None)
chk(f"Binance -2013, но в истории ордеров FILLED -> сделка ⚡ записана (вход {t and t['entry']})", t is not None and t["real"] and abs(t["entry"] - 0.0006964) < 1e-12 and o["status"] == "FILLED")
chk(f"её стоп поставлен на бирже: {[p for b, k, p in placed if k == 'STOP_MARKET']}", any(k == "STOP_MARKET" and b == "TURBOUSDT" for b, k, _ in placed))
chk("нет записи «коснулась, но не исполнилась»", not any("touched but not filled" in m for m in logs))
# (2) unknown both ways after the cancel attempt -> nothing decided
o = mk(); B["hist"] = None; logs.clear(); placed.clear()
with V._dlm_lock:
    V._DLM["orders"] = [o]; V._DLM["trades"] = []
V.dlm_bn_tick([o], [])
chk(f"ордер не найден ни там, ни там -> ничего не решено (статус {o['status']}, сделок {len(V._DLM['trades'])})", o["status"] == "OPEN" and not V._DLM["trades"] and not any("touched but not filled" in m for m in logs))
B["order_err"] = False; B["hist"] = "FILLED"
o["until"] = time.time() - 1   # the next tick: the order readable now, its time up — and it was filled
B["order_err"] = True
V.dlm_bn_tick([o], [])
chk("следующий такт: ордер нашёлся исполненным -> сделка записана", any(x["symbol"] == "TURBO_USDT" for x in V._DLM["trades"]))
# (2b) a stale "NEW" answer while it was filled: the cancel says "unknown order", the re-read still "NEW" -> not decided
STALE = {"n": 0}
def req2(method, path, params=None):
    if path == "/fapi/v1/order" and method == "GET":
        STALE["n"] += 1
        return {"orderId": params["orderId"], "status": "NEW", "executedQty": "0"} if STALE["n"] <= 2 else {"orderId": params["orderId"], "status": "FILLED", "executedQty": "100000", "avgPrice": "0.0006964"}
    return req(method, path, params)
V.bnf_req = req2; V.bnf_place_cond = lambda bsym, s, kind, px, dual: ("algo", "x")
o = mk(); logs.clear()
with V._dlm_lock:
    V._DLM["orders"] = [o]; V._DLM["trades"] = []
V.dlm_bn_tick([o], [])
chk(f"устаревшее «NEW» при позиции на монете -> не решено (статус {o['status']})", o["status"] == "OPEN" and not V._DLM["trades"] and not any("touched but not filled" in m for m in logs))
V.dlm_bn_tick([o], [])
chk("следующий такт: ордер FILLED -> сделка записана", any(x["symbol"] == "TURBO_USDT" for x in V._DLM["trades"]))
V.bnf_req = req
# (3) -4509
V._BNF.pop("pre_off", None); logs.clear(); calls = []
def place_4509(bsym, s, kind, px, dual):
    calls.append(kind); raise V.BinanceError(-4509, "Time in Force (TIF) GTE can only be used with open positions.")
V.bnf_place_cond = place_4509
o1, o2 = mk(), mk(); o2["real"]["bsym"] = "HOMEUSDT"
V._dlm_bn_pre_exits(o1, 0.00065); V._dlm_bn_pre_exits(o2, 0.0048)
chk(f"-4509: спрошено один раз ({calls}), дальше лимитки без стопа до позиции", calls == ["STOP_MARKET"] and V._BNF.get("pre_off") and o2["real"].get("pre_sl_err"))
note = [m for m in logs if "-4509" in m]
chk(f"одна запись в журнале, уровень {V.log_level(note[0]) if note else None}", len(note) == 1 and V.log_level(note[0]) == "warn")
# (4) a partly filled limit expired by the exchange (MOVE): still the bot's
def req3(method, path, params=None):
    if path == "/fapi/v1/allOrders":
        return [{"orderId": 3095242810, "status": "EXPIRED", "side": "BUY", "reduceOnly": False, "closePosition": False, "executedQty": "6271",
                 "updateTime": 5, "clientOrderId": "vpdlm1794147501000"},
                {"orderId": 1, "status": "FILLED", "side": "SELL", "reduceOnly": True, "closePosition": False, "executedQty": "10", "updateTime": 9, "clientOrderId": "x"}]
    return {}
V.bnf_req = req3; V._ADOPT["who"] = {}; V._ADOPT["owner"] = {}
chk("частично исполненная и истёкшая лимитка ⚡ — позиция бота (модуль ⚡)", V.bn_pos_by_bot("MOVEUSDT", 1, 0.005667) and V.bn_pos_owner("MOVEUSDT", 1, 0.005667) == "dlm")
def req4(method, path, params=None):
    if path == "/fapi/v1/allOrders":
        return [{"orderId": 5, "status": "EXPIRED", "side": "BUY", "reduceOnly": False, "closePosition": False, "executedQty": "0", "updateTime": 5, "clientOrderId": "vpdlm1"},
                {"orderId": 6, "status": "FILLED", "side": "BUY", "reduceOnly": False, "closePosition": False, "executedQty": "3", "updateTime": 4, "clientOrderId": "android_1"}]
    return {}
V.bnf_req = req4; V._ADOPT["who"] = {}; V._ADOPT["owner"] = {}
chk("ручная позиция (исполнен ручной ордер, лимитка бота не исполнилась) — не бота", not V.bn_pos_by_bot("XUSDT", 1, 1.0))
print("t_fill787 OK" if ok else "t_fill787 FAIL")
