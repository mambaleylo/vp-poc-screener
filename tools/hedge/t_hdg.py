"""🪞 hedge mirror on a fake two-account exchange"""
import sys, io, contextlib, itertools, tempfile, os
sys.argv = ["x"]
sys.path.insert(0, "/home/user/vp-poc-screener")
with contextlib.redirect_stdout(io.StringIO()):
    import vp_poc_screener as V
V.HDG_STATE_FILE = os.path.join(tempfile.mkdtemp(), "hdg.json")
V.GATE_API_KEY, V.GATE_API_SECRET = "k", "s"
V.MODULE_CREDENTIALS["zones"] = {"api_key": "k2", "api_secret": "s2"}
V.AUTOTRADE_DRY_RUN = False
TG = []
V.send_telegram = lambda text, category=None: TG.append(text)
V.log_error = lambda *a, **k: None
V.get_contract_spec = lambda c: {"quanto_multiplier": 1, "order_size_min": 1, "leverage_max": 100, "order_price_round": 0.01}
V._dual_mode_cache_by_acc.clear()
ids = itertools.count(100)
EX = {"default": {"pos": {}, "ord": {}, "lev": {}}, "zones": {"pos": {}, "ord": {}, "lev": {}}}
BAL = {"default": 1000.0, "zones": 1500.0}
PRICE = {"BTC_USDT": 50000.0, "ETH_USDT": 100.0, "SOL_USDT": 20.0}
def liq_of(c, size, lev, entry):
    lev = float(lev or 10)
    return round(entry * (1 - 0.9 / lev), 4) if size > 0 else round(entry * (1 + 0.9 / lev), 4)
def fake(method, path, query_string="", body=None, **k):
    acc = V.current_account_id(); ex = EX[acc]
    if path == "/futures/usdt/accounts":
        return {"in_dual_mode": False, "total": str(BAL[acc]), "unrealised_pnl": "0"}
    if path == "/futures/usdt/positions" and method == "GET":
        return [dict(contract=c, **p) for c, p in ex["pos"].items()]
    if path == "/futures/usdt/price_orders" and method == "GET":
        return list(ex["ord"].values())
    if path.startswith("/futures/usdt/price_orders/") and method == "DELETE":
        return ex["ord"].pop(path.rsplit("/", 1)[1], None)
    if path == "/futures/usdt/price_orders" and method == "POST":
        i = str(next(ids)); ex["ord"][i] = dict(body, id=i); return {"id": i}
    if path.endswith("/leverage"):
        c = path.split("/")[-2]; ex["lev"][c] = query_string; return {}
    if path == "/futures/usdt/orders":
        c = body["contract"]; px = PRICE[c]
        if body.get("close"):
            ex["pos"].pop(c, None); return {"fill_price": str(px)}
        lev = (ex["lev"].get(c, "leverage=10").split("&")[0].split("=")[1])
        ex["pos"][c] = {"size": body["size"], "entry_price": str(px), "leverage": lev, "cross_leverage_limit": "0",
                        "liq_price": str(liq_of(c, body["size"], lev, px))}
        return {"fill_price": str(px), "id": 1}
    if path == "/futures/usdt/position_close":
        return [{"time": 1790000000, "pnl": "-12", "pnl_pnl": "-10", "pnl_fee": "-1.5", "pnl_fund": "-0.5", "contract": "ETH_USDT"},
                {"time": 1790100000, "pnl": "5", "pnl_pnl": "7", "pnl_fee": "-1.5", "pnl_fund": "-0.5", "contract": "SOL_USDT"}]
    raise RuntimeError(f"unexpected {method} {path}")
V.gate_signed_request = fake
ok = bad = 0
def check(name, cond):
    global ok, bad
    if cond: ok += 1
    else: bad += 1; print("FAIL", name)
def src_open(c, size, lev="10", orders=()):
    EX["default"]["pos"][c] = {"size": size, "entry_price": str(PRICE[c]), "leverage": lev, "cross_leverage_limit": "0", "liq_price": "0"}
    for price, rule in orders:
        i = str(next(ids)); EX["default"]["ord"][i] = {"id": i, "initial": {"contract": c, "size": 0, "price": "0", "close": True, "tif": "ioc"},
                                                     "trigger": {"price": str(price), "rule": rule, "price_type": 0}, "order_type": ""}
def dst_orders(c):
    return sorted((float(o["trigger"]["price"]), o["trigger"]["rule"], o["trigger"]["price_type"]) for o in EX["zones"]["ord"].values() if o["initial"]["contract"] == c)
V._HDG["cfg"] = {"on": False, "src": "default", "dst": "zones", "mult": 2.0, "tg": True}
V._HDG["loaded"] = True
# 1. a position already open when switched on is left alone
src_open("BTC_USDT", 3)
c = V.app.test_client()
r = c.post("/api/hdg/config", json={"on": True}).get_json()
check("switch on", r["ok"])
V.hdg_tick()
check("old position not mirrored", "BTC_USDT" not in EX["zones"]["pos"])
# 2. a new long with take 110 / stop 95 -> a short x2, same leverage; take->stop (beyond the liquidation -> before it), stop->take
src_open("ETH_USDT", 10, "10", [(110, 1), (95, 2)])
V.hdg_tick()
p = EX["zones"]["pos"].get("ETH_USDT")
check("mirror opened short: 10*100/1000=1% -> 2% of 1500 = 30$ = 0.3 ETH... size 30", p and p["size"] == -30)
check("same leverage", EX["zones"]["lev"].get("ETH_USDT") == "leverage=10")
liq = float(p["liq_price"]) if p else 0
o = dst_orders("ETH_USDT")
print("  ETH mirror liq", liq, "orders", o)
check("mirror take at the source stop", (95.0, 2, 0) in o)
check("mirror stop clamped before the liquidation (mark price)", any(r_ == 1 and pt == 1 and liq - 0.2 < pr < liq for pr, r_, pt in o))
check("clamp notified", any("ликвидац" in t for t in TG))
# 3. the source take moved to 104 (within the liquidation) -> the mirror stop at 104 exactly
for i, od in list(EX["default"]["ord"].items()):
    if od["initial"]["contract"] == "ETH_USDT" and od["trigger"]["rule"] == 1:
        EX["default"]["ord"].pop(i)
src_open("ETH_USDT", 10, "10", [(104, 1)])
V.hdg_tick()
o = dst_orders("ETH_USDT")
print("  ETH after move", o)
check("old stop replaced, new at 104", (104.0, 1, 0) in o and not any(r_ == 1 and pr != 104.0 for pr, r_, pt in o))
check("no duplicate orders", len(o) == 2)
# 4. closed by hand on the source -> the mirror closes, its orders cancelled
EX["default"]["pos"].pop("ETH_USDT")
for i in [i for i, od in EX["default"]["ord"].items() if od["initial"]["contract"] == "ETH_USDT"]:
    EX["default"]["ord"].pop(i)
V.hdg_tick()
check("mirror closed", "ETH_USDT" not in EX["zones"]["pos"])
check("mirror orders cancelled", not dst_orders("ETH_USDT"))
# 5. a new short with no take / stop -> a long x2 + a stop right before the liquidation
src_open("SOL_USDT", -7, "5")
V.hdg_tick()
p = EX["zones"]["pos"].get("SOL_USDT")
check("long mirror 3x contracts (x2 share, 1.5x deposit)", p and p["size"] == 21)
o = dst_orders("SOL_USDT")
print("  SOL mirror liq", p and p["liq_price"], "orders", o)
check("liquidation guard stop", len(o) == 1 and o[0][1] == 2 and o[0][0] > float(p["liq_price"]))
# 6. the mirror closed on its own -> not reopened while the source is still open
EX["zones"]["pos"].pop("SOL_USDT")
V.hdg_tick(); V.hdg_tick()
check("not reopened", "SOL_USDT" not in EX["zones"]["pos"])
check("guard cancelled", not dst_orders("SOL_USDT"))
# then the source closes and opens again -> a new mirror
EX["default"]["pos"].pop("SOL_USDT"); V.hdg_tick()
src_open("SOL_USDT", -4, "5"); V.hdg_tick()
check("reopened source -> new mirror", EX["zones"]["pos"].get("SOL_USDT", {}).get("size") == 12)
# 7. the ignored BTC closes and opens again -> mirrored now
EX["default"]["pos"].pop("BTC_USDT"); V.hdg_tick()
src_open("BTC_USDT", 1); V.hdg_tick()
check("BTC mirrored after a new open", EX["zones"]["pos"].get("BTC_USDT", {}).get("size") == -3)
# 8. a foreign position on the target account is not touched
EX["zones"]["pos"]["ETH_USDT"] = {"size": 5, "entry_price": "100", "leverage": "10", "cross_leverage_limit": "0", "liq_price": "91"}
src_open("ETH_USDT", 3); V.hdg_tick()
check("foreign position untouched", EX["zones"]["pos"]["ETH_USDT"]["size"] == 5)
check("error recorded", V._HDG["pairs"]["ETH_USDT|long"]["status"] == "error")
# 9. switching accounts refused while mirrors are open; history; status JSON
r = c.post("/api/hdg/config", json={"dst": "neuro"})
check("account change refused while open", r.status_code == 400)
st = c.get("/api/hdg/status").get_json()
check("status", len(st["open"]) == 2 and st["cfg"]["on"])
# 10. a state reload keeps the pairs (restart)
V.hdg_save(); saved = dict(V._HDG["pairs"]); V._HDG["pairs"] = {}; V.hdg_load()
check("state survives a restart", set(V._HDG["pairs"]) == set(saved))
print("ok", ok, "fail", bad)
print("\n".join("TG: " + t for t in TG))
