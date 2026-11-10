"""v0.99.792 — the network (the user: "1 и 2 пункт надо сделать"):
(1) ⚡ arming: a connection error / Binance busy while the limit goes on the exchange is not "no trade" — the order waits and is
    placed on the next pass (was: SKIPPED for good); a real refusal still skips it; a request whose answer was lost: Binance is
    asked by the order's own client id before anything is sent again — the limit that did land is taken (never a second one),
    one that filled meanwhile too, one that did not land is sent again under the same id; an error after the limit stands never
    drops its id;
(2) the scan: the coins whose just-closed bar could not be read are returned and scanned again later (the catch-up's way: an
    order the price reached meanwhile is not armed), a scan that could not run in its 10 minutes is done whole later; a re-scan
    adds to the bar's numbers; the jobs end when the coins are read, after the tries, or when the bar's orders would be dead"""
import time
from common import V
ok = True
def chk(nm, c):
    global ok
    print(("OK  " if c else "FAIL") + " " + nm); ok &= bool(c)
errs = []; V.log_error = lambda m: errs.append(str(m))
BE = V.BinanceError
def net(): e = BE(None, "нет связи: timeout"); e.net = True; return e
chk("сетевые ошибки распознаются, отказ — нет", V.bnf_transient(net()) and V.bnf_transient(BE(-1007, "Timeout waiting for response")) and V.bnf_transient(BE(None, "bad gateway", 502))
    and not V.bnf_transient(BE(-2019, "Margin is insufficient")) and not V.bnf_transient(BE(None, "ключи Binance не заданы")) and not V.bnf_transient(ValueError("x")))

# ---- (1) the arming
now = time.time()
def order(sym="AAA_USDT", lv=1.0):
    return {"id": f"dlm_{sym}_1_{int(now)}", "symbol": sym, "side": 1, "lv": lv, "atr": 0.05, "score": 0.9, "bs": 14400, "st": "wick4h", "t0": int(now) - 100,
            "until": now + 40000, "status": "OPEN", "real": None}
V.DLM_BINANCE = True; V.AUTOTRADE_DRY_RUN = False; V.DLM_PRIO = False
V._dlm_prices = lambda syms: {s: 1.01 for s in syms}   # 0.2 ATR above the level: within the arming distance
o = order(); V._DLM["orders"] = [o]; V._DLM["trades"] = []
seq = [net(), None]
def place(o_):
    e = seq.pop(0)
    if e: raise e
    o_["real"] = {"status": "LIMIT", "ex": "binance", "id": "77", "bsym": "AAAUSDT", "scl": 1.0, "qty": 10, "price": 1.0}
V.dlm_real_place = place
V._dlm_arm(now)
chk(f"обрыв связи при выставлении: заявка ждёт, не «пропущена»: «{o.get('hold')}»", o["real"] is None and "связь" in (o.get("hold") or "") and o["status"] == "OPEN")
V._dlm_arm(now + 5)
chk("следующий проход — лимитка выставлена", (o.get("real") or {}).get("id") == "77")
o2 = order("BBB_USDT"); V._DLM["orders"] = [o2]
def refuse(o_): raise BE(-2019, "Margin is insufficient")
V.dlm_real_place = refuse; V._dlm_arm(now)
chk("настоящий отказ Binance — как раньше, сделки нет", (o2.get("real") or {}).get("status") == "SKIPPED")
o3 = order("CCC_USDT"); V._DLM["orders"] = [o3]
def after(o_):
    o_["real"] = {"status": "LIMIT", "ex": "binance", "id": "88", "bsym": "CCCUSDT", "scl": 1.0, "qty": 10, "price": 1.0}; raise net()
V.dlm_real_place = after; V._dlm_arm(now)
chk("ошибка уже после того, как лимитка встала: её номер не теряется", (o3.get("real") or {}).get("id") == "88")
n_log = len([e for e in errs if "again on the next pass" in e]); o4 = order("DDD_USDT"); V._DLM["orders"] = [o4]
def always(o_): raise net()
V.dlm_real_place = always
for i in range(8): V._dlm_arm(now + i * 5)
chk("долгий обрыв: в журнале одна строка в минуту, не каждые 5 с", len([e for e in errs if "again on the next pass" in e]) - n_log == 1)

# ---- (1) the lost answer: dlm_bn_place against a small fake Binance
BX = {"orders": {}, "next": 500, "posts": [], "lose": 0, "fail_get": 0, "pos": {}}
def fake_req(method, path, params=None, **k):
    p = dict(params or {})
    if path == "/fapi/v1/leverage": return {}
    if path == "/fapi/v1/order" and method == "POST":
        BX["posts"].append(p)
        if any(x["clientOrderId"] == p["newClientOrderId"] and x["status"] in ("NEW", "PARTIALLY_FILLED") for x in BX["orders"].values()):
            raise BE(-4116, "ClientOrderId is duplicated.")
        if BX["lose"] in (1, 2):   # 1: placed, the answer lost; 2: not placed at all
            placed = BX["lose"] == 1; BX["lose"] = 0
            if placed:
                BX["next"] += 1
                BX["orders"][BX["next"]] = {"orderId": BX["next"], "clientOrderId": p["newClientOrderId"], "status": "NEW", "origQty": p["quantity"], "price": p["price"],
                                            "timeInForce": p["timeInForce"], "symbol": p["symbol"], "time": int(time.time() * 1000), "executedQty": "0"}
            raise net()
        BX["next"] += 1
        BX["orders"][BX["next"]] = {"orderId": BX["next"], "clientOrderId": p["newClientOrderId"], "status": "NEW", "origQty": p["quantity"], "price": p["price"],
                                    "timeInForce": p["timeInForce"], "symbol": p["symbol"], "time": int(time.time() * 1000), "executedQty": "0"}
        return dict(BX["orders"][BX["next"]])
    if path == "/fapi/v1/order" and method == "GET":
        if BX["fail_get"]: BX["fail_get"] -= 1; raise net()
        x = next((x for x in BX["orders"].values() if x["clientOrderId"] == p.get("origClientOrderId") or str(x["orderId"]) == str(p.get("orderId"))), None)
        if x is None: raise BE(-2013, "Order does not exist.")
        return dict(x)
    if path == "/fapi/v1/allOrders": return [dict(x) for x in BX["orders"].values()]
    raise AssertionError(path)
V.bnf_req = fake_req
V.bn_map = lambda sym: (sym.replace("_", ""), 1.0)
V.bnf_symbols = lambda: {s: {"tick": 0.001, "step": 0.1, "min_qty": 0.1, "min_notional": 5.0, "ok": True} for s in ("AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT", "EEEUSDT")}
V.bnf_positions = lambda: dict(BX["pos"]); V.bnf_dual = lambda: False; V.bnf_tiers = lambda b: [(1e9, 0.5, 20)]
V.bnf_account = lambda: {"equity": 1000.0, "free": 1000.0}; V.dlm_osc_mult = lambda *a, **k: 1.0; V.dlm_load_mult = lambda: 1.0
V.bn_margin_mode = lambda b: "ISOLATED"; V._dlm_bn_pre_exits = lambda o_, sl: None; V._BNF["lev_cap"] = None
V._DLM["model"] = dict(V.dlm_model() or {}, rule=(V.dlm_model() or {}).get("rule") or {})
def try_place(o_):
    try: V.dlm_bn_place(o_); return None
    except BE as e: return e
# the answer lost, the limit did land
a = order("AAA_USDT"); BX["lose"] = 1; e1 = try_place(a)
chk("ответ потерян: заявка без номера, свой id запомнен", e1 is not None and V.bnf_transient(e1) and a.get("real") is None and str(a.get("cid", "")).startswith("vpdlm"))
BX["fail_get"] = 1; e2 = try_place(a)
chk("связи всё ещё нет: ничего не отправлено повторно", e2 is not None and len(BX["posts"]) == 1 and a.get("cid"))
e3 = try_place(a)
chk(f"связь вернулась: вставшая лимитка найдена по id, второй нет: {a.get('real', {}).get('id')}", e3 is None and len(BX["posts"]) == 1 and len(BX["orders"]) == 1
    and a["real"]["id"] == str(list(BX["orders"])[0]) and a["real"]["lev"] and a["real"]["risk"] and "cid" not in a and a["real"]["qty"] > 0)
# the request never reached Binance: sent again under the same id
b = order("BBB_USDT"); BX["lose"] = 2; n0 = len(BX["posts"]); e1 = try_place(b); cid = b.get("cid"); e2 = try_place(b)
chk("запрос не дошёл: отправлен снова под тем же id, лимитка одна", e1 is not None and e2 is None and len(BX["posts"]) - n0 == 2 and BX["posts"][-1]["newClientOrderId"] == cid
    and sum(1 for x in BX["orders"].values() if x["symbol"] == "BBBUSDT") == 1 and b["real"]["id"])
# the lost limit filled before the next pass: taken as the order's own (the tick opens the trade), never "a foreign position"
c = order("CCC_USDT"); BX["lose"] = 1; try_place(c)
x = next(x for x in BX["orders"].values() if x["symbol"] == "CCCUSDT"); x["status"] = "FILLED"; x["executedQty"] = x["origQty"]; BX["pos"]["CCCUSDT"] = [{"amt": 1.0}]
e = try_place(c)
chk("потерянная лимитка успела исполниться: взята как своя, не «чужая позиция»", e is None and (c.get("real") or {}).get("id") == str(x["orderId"]) and not c.get("hold"))
BX["pos"].clear()
# it stood and was cancelled meanwhile: a new limit under a new id
d = order("DDD_USDT"); BX["lose"] = 1; try_place(d); x = next(x for x in BX["orders"].values() if x["symbol"] == "DDDUSDT"); x["status"] = "CANCELED"; old = d["cid"]
time.sleep(0.01); e = try_place(d)
chk("потерянная лимитка уже снята: новая под новым id", e is None and d["real"]["id"] != str(x["orderId"]) and BX["posts"][-1]["newClientOrderId"] != old)
# -4116: the POST itself says the id is taken
e_ = order("EEE_USDT"); e_["cid"] = "vpdlm123"; BX["next"] += 1
BX["orders"][BX["next"]] = {"orderId": BX["next"], "clientOrderId": "vpdlm123", "status": "NEW", "origQty": "5", "price": "1.000", "timeInForce": "GTD", "symbol": "EEEUSDT", "time": 1, "executedQty": "0"}
_by = V.bnf_order_by_cid; first = [True]
def by_cid(bsym, cid_):
    if first[0]: first[0] = False; return None   # "unknown" for seconds (v0.99.787)
    return _by(bsym, cid_)
V.bnf_order_by_cid = by_cid; n0 = len(BX["posts"]); e = try_place(e_); V.bnf_order_by_cid = _by
chk("Binance сначала «не знает» лимитку, POST отвечает «id занят»: взята она, второй нет", e is None and e_["real"]["id"] == str(BX["next"]) and len(BX["posts"]) - n0 == 1
    and sum(1 for x in BX["orders"].values() if x["symbol"] == "EEEUSDT") == 1)

# ---- (2) the scan
m = V.dlm_model(); st = V._dlm_streams(m)[0]; bs = int(st["bar_sec"]); t_bar = int(now // bs * bs)
coins = V.dlm_coins(); down = set(coins[:7])
V._dlm_chart = lambda sym, st_, n, t: None if sym in down else [{"time": t - bs, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1, "bn": 1}]
made = []
def cands(bars, bb, **k):
    return []
V.dlm_candidates4 = cands; V._DLM.update(orders=[], trades=[], scan=None); V._DLM.pop("rescan", None); V.dlm_save = lambda: None
miss = V.dlm_scan(t_bar, st)
chk(f"просмотр: монеты без свечи возвращены ({len(miss)} из {len(coins)}), в цифрах бара просмотрено {V._DLM['scan']['by'][st['name']]['coins']}", set(miss) == down
    and V._DLM["scan"]["by"][st["name"]]["coins"] == len(coins) - 7)
V.dlm_rescan_add(st, t_bar, miss, now); j = V._DLM["rescan"][0]
chk("поставлен повтор через 2 минуты, до конца жизни заявок бара", j["syms"] == sorted(down) and 100 < j["t"] - now < 140 and j["until"] == t_bar + int(st.get("alive_bars", 4)) * bs)
chk("раньше срока повтор не идёт", V.dlm_rescan_run(now + 60) == 0 and j["n"] == 0)
# the data are back for 5 of the 7; two of them give an order: one the price already reached, one not
back = sorted(down)[:5]; down -= set(back)
def cands2(bars, bb, **k):
    return [{"side": 1, "lv": 0.9, "atr": 0.05, "f": [0.0] * 40}]
V.dlm_candidates4 = cands2; V.zm_tree_pred = lambda t_, f: 99.0; V._sl_too_tight = lambda *a: False
hit = {f"dlm_{back[0]}_1_{t_bar}": (1, 0.1, t_bar, 0.9)}   # reached meanwhile
V._dlm_hit = lambda o_, t: hit.get(o_["id"].replace("_" + st["name"], ""), False)
V._DLM.pop("cu_settle", None); added = V.dlm_rescan_run(now + 130)
new = {o_["symbol"]: o_ for o_ in V._DLM["orders"]}
chk(f"повтор: по вернувшимся монетам заявки появились ({added})", added == 5 and set(new) == set(back) and all(o_.get("from_cu") for o_ in new.values()))
chk("цена уже дошла до уровня — заявка не идёт на биржу (ждёт расчёта как виртуальная), остальные идут", new[back[0]].get("cu") and not any(new[c_].get("cu") for c_ in back[1:])
    and V._DLM.get("cu_settle") is True)
b_ = V._DLM["scan"]["by"][st["name"]]
chk(f"цифры бара дополнены: просмотрено {b_['coins']}, из них повтором {b_.get('rescan')}", b_["coins"] == len(coins) - 2 and b_.get("rescan") == 5 and b_["orders"] == 5)
j = V._DLM["rescan"][0]
chk("две монеты так и без свечи — повтор остаётся, следующий позже", j["syms"] == sorted(down) and j["n"] == 1 and j["t"] > now + 130)
for k in range(2, 12):
    if not V._DLM.get("rescan"): break
    V._DLM["rescan"][0]["t"] = 0; V.dlm_rescan_run(now + 200)
chk("свечи так и не появились — повторы заканчиваются сами", not V._DLM.get("rescan"))
V.dlm_rescan_add(st, t_bar - 10 * bs, ["X_USDT"], now); V._DLM["rescan"][0]["t"] = 0; V.dlm_rescan_run(now)
chk("бар, чьи заявки уже не живут, не досматривается", not V._DLM.get("rescan"))
# the whole scan that could not run
down.clear(); V._DLM.update(orders=[]); V.dlm_rescan_add(st, t_bar, None, now); V._DLM["rescan"][0]["t"] = 0; V._dlm_hit = lambda o_, t: False
added = V.dlm_rescan_run(now)
chk(f"просмотр, не успевший за 10 минут, сделан целиком позже ({added} заявок), заявки можно выставлять", added == len(coins) and not V._DLM.get("rescan")
    and not any(o_.get("cu") for o_ in V._DLM["orders"]))
V.dlm_rescan_add(st, t_bar, [], now); chk("пропущенных нет — повтор не ставится", not V._DLM.get("rescan"))
# ---- /orders (the user: "команду показывающую количество лимиток в p/r, лимиток, выставленных на бирже и количество сделок активных")
V._PRX["trades"] = [{"status": "PENDING", "lv": 1.0, "hour": int(now), "wait": 3, "side": 1}, {"status": "PENDING", "lv": 1.0, "hour": int(now), "wait": 3, "side": -1},
                    {"status": "PENDING", "lv": 1.0, "hour": int(now) - 5 * 3600, "wait": 3, "side": 1},   # its wait is over
                    {"status": "PENDING", "lv": 1.0, "hour": int(now), "wait": 3, "side": 1, "rt": True},   # reached: not a limit any more
                    {"status": "OPEN", "side": 1, "real": False, "hour": int(now)}]
V._DLM["orders"] = [dict(order("A_USDT"), real={"id": "1"}), dict(order("B_USDT"), real={"id": "2"}, side=-1), dict(order("C_USDT"), real={"id": "3"}),
                    order("D_USDT"), dict(order("E_USDT"), real={"status": "SKIPPED"}), dict(order("F_USDT"), status="EXPIRED", real={"id": "9"})]
V._DLM["trades"] = [{"status": "OPEN", "real": {"bsym": "XUSDT"}, "side": 1}, {"status": "OPEN", "real": None, "side": 1}, {"status": "CLOSED", "real": {"bsym": "Y"}, "side": 1}]
V._BNO["pos"] = {"X_USDT": {"mode": "prv"}, "Y_USDT": {"mode": "smc"}, "Z_USDT": {"mode": "smc"}}
for st_ in (V._EMX, V._SMC, V._HTF, V._CFL): st_["trades"] = []
V._SMC["trades"] = [{"status": "OPEN", "real": False}]
txt = V.bot_orders_text(now)
print("   " + txt.replace("\n", "\n   "))
chk("/orders: лимитки P/R 2 (лонг 1, шорт 1)", "Лимитки P/R (ждут цену): 2 — лонг 1, шорт 1" in txt)
chk("/orders: лимитки ⚡ на бирже 3, ждут цену 1", "Лимитки ⚡ на бирже: 3 — лонг 2, шорт 1; ещё ждут подхода цены: 1" in txt)
chk("/orders: активные сделки на бирже 4 по модулям", "Активные сделки на бирже: 4 — ⚡ 1, P/R 1, 🧱 SMC 2" in txt)
chk("/orders: виртуальные 3", "Виртуальные сделки (без денег): 3" in txt)
sent = []; V.tg_outbox_push = lambda t: sent.append(t)
chk("команда /orders (и /count) через Telegram, есть в /help", V.bot_command("/orders") and V.bot_command("/count") and len(sent) == 2 and sent[0].startswith("📋") and "/orders" in V.BOT_COMMANDS_HELP)
V._DLM["loaded"] = False; chk("сразу после запуска — честная пометка", "записи ещё читаются" in V.bot_orders_text(now)); V._DLM["loaded"] = True
print("t_net792 OK" if ok else "t_net792 FAIL")
