"""v0.99.795 — «Режим разгона»: (1) off -> the ⚡ limit sized as always; (2) on with a stake -> the day's first ⚡ limit: isolated, the
loss at the emergency stop = the stake (never cut), the leverage leaving the liquidation _dlm_liq_buf() x beyond that stop; the next limit while
it is armed -> a usual one; (3) the stake does not fit (the coin's leverage / the free margin) -> that limit usual, the next one of
the day tried; (4) the fill -> the trade carries the stake, the day taken: no second «разгон» today, again tomorrow (Moscow day);
(5) the close -> the tally in $ from the fills, Telegram; the losses reaching the limit (in stakes) switch the mode off and say so;
(6) the settings saved / read; the switch on again -> the limit counts from then; (7) the settings group, the status, no page errors"""
import time, json, math
from common import V
ok = True
def chk(nm, c):
    global ok
    print(("OK  " if c else "FAIL") + " " + nm); ok &= bool(c)
errs = []; V.log_error = lambda m: errs.append(str(m)); tg = []; V.send_telegram = lambda m, **k: tg.append(m)
BE = V.BinanceError
BX = {"orders": {}, "next": 100, "posts": [], "lev": {}, "mt": {}}
def fake_req(method, path, params=None, **k):
    p = dict(params or {})
    if path == "/fapi/v1/leverage": BX["lev"][p["symbol"]] = int(p["leverage"]); return {}
    if path == "/fapi/v1/marginType": BX["mt"][p["symbol"]] = p["marginType"]; return {}
    if path == "/fapi/v1/order" and method == "POST":
        BX["posts"].append(p); BX["next"] += 1
        BX["orders"][BX["next"]] = dict(p, orderId=BX["next"], status="NEW", origQty=p["quantity"], executedQty="0", clientOrderId=p["newClientOrderId"])
        return dict(BX["orders"][BX["next"]])
    raise AssertionError(path)
V.bnf_req = fake_req; V.bn_map = lambda sym: (sym.replace("_", ""), 1.0)
V.bnf_symbols = lambda: {s: {"tick": 0.0001, "step": 0.1, "min_qty": 0.1, "min_notional": 5.0, "ok": True} for s in ("AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT")}
V.bnf_positions = lambda: {}; V.bnf_dual = lambda: False
TIERS = {"AAAUSDT": [(1e9, 0.005, 50)], "BBBUSDT": [(1e9, 0.005, 50)], "CCCUSDT": [(1e9, 0.02, 4)], "DDDUSDT": [(1e9, 0.005, 50)]}
V.bnf_tiers = lambda b: TIERS[b]; V._BNF["lev_cap"] = 20
ACC = {"equity": 1000.0, "free": 1000.0}; V.bnf_account = lambda: dict(ACC)
V.dlm_osc_mult = lambda *a, **k: 1.0; V.dlm_load_mult = lambda: 1.0; V._dlm_bn_pre_exits = lambda o_, sl: None
V.bn_margin_mode = lambda b: "CROSSED"; V.bn_heat_cap = lambda risk, eq, mode=None: (risk, None)
V.save_settings = lambda: None; V.dlm_save = lambda: None
now = time.time()
V._DLM.update(orders=[], trades=[], boost=None, loaded=True); V._DLM["model"] = dict(V.dlm_model() or {})
def order(sym, lv=1.0, atr=0.02, side=1):
    o = {"id": f"dlm_{sym}_{side}_{int(now)}", "symbol": sym, "side": side, "lv": lv, "atr": atr, "score": 0.9, "bs": 14400, "st": "close2h", "t0": int(now),
         "until": now + 40000, "status": "OPEN", "real": None}
    V._DLM["orders"].append(o); return o
rule = (V._DLM["model"].get("rule") or {})
# (1) off
V.DLM_BOOST = False; V.DLM_BOOST_USD = 20.0
a = order("AAA_USDT"); V.dlm_bn_place(a)
chk(f"выключен — обычная лимитка ⚡ (кросс, без ставки): риск {a['real'].get('risk')}%", a["real"]["margin"] == "CROSSED" and "boost" not in a["real"])
V._DLM["orders"] = []
# (2) on: the day's first limit
V.apply_settings({"dlm_boost": True, "dlm_boost_usd": 20, "dlm_boost_cap": 5})
b = order("BBB_USDT"); V.dlm_bn_place(b); r = b["real"]
sl, kx = V._dlm_size_stop(b, rule); em = abs(b["lv"] - sl) / b["lv"]
loss_at_stop = r["qty"] * abs(b["lv"] - sl)
chk(f"включён — первая лимитка дня: изолированная, ставка ${r.get('boost')}, потеря на аварийном стопе ${loss_at_stop:.2f}", r.get("boost") == 20 and r["margin"] == "ISOLATED"
    and BX["mt"]["BBBUSDT"] == "ISOLATED" and 19.9 <= loss_at_stop <= 20 * 1.03)
liq = 1 / r["lev"]; buf = V._dlm_liq_buf()
chk(f"плечо {r['lev']}x: ликвидация ({100 * liq:.1f}% от входа) дальше аварийного стопа ({100 * em:.1f}%) в {buf:g} раза", liq >= buf * em * 0.99 and BX["lev"]["BBBUSDT"] == r["lev"])
c = order("AAA_USDT"); V.dlm_bn_place(c)
chk("пока разгонная лимитка стоит — следующие лимитки обычные", "boost" not in c["real"] and c["real"]["margin"] == "CROSSED")
# (3) the stake does not fit: the coin's max 4x
V._DLM["orders"] = [x for x in V._DLM["orders"] if x is not b]; b["status"] = "EXPIRED"   # the day's «разгон» limit expired unfilled
ACC.update(free=60); d = order("CCC_USDT"); V.dlm_bn_place(d); ACC.update(free=1000)
chk(f"монета не даёт поставить ставку целиком (плечо до 4x — нужна маржа ~$83, свободно $60) — лимитка обычная", "boost" not in d["real"])
e = order("DDD_USDT"); V.dlm_bn_place(e)
chk("следующая лимитка дня, которая влезает целиком, — разгонная", e["real"].get("boost") == 20)
# (4) the fill -> the trade carries the stake, the day is taken
oid = e["real"]["id"]
BX["orders"][int(oid)].update(status="FILLED", executedQty=str(e["real"]["qty"]), avgPrice="1.0")
V.bnf_order = lambda bsym, i: dict(BX["orders"][int(i)])
V._dlm_bn_take_over = lambda *a, **k: None; V._dlm_bn_exits = lambda *a, **k: None; V._dlm_bn_fills = lambda now=None: False
V.bnf_positions = lambda: {"DDDUSDT": [{"amt": e["real"]["qty"], "mark": 1.0}]}
tg.clear(); V.dlm_bn_tick([e], [])
tr = [t for t in V._DLM["trades"] if t["symbol"] == "DDD_USDT"]
chk(f"исполнилась — сделка несёт ставку, день занят, сообщение: «{(tg or [''])[0][:60]}…»", tr and tr[0]["real"].get("boost") == 20 and V._boost_st()["day"] == V._msk_day(time.time()) and tg)
f = order("AAA_USDT"); V.dlm_bn_place(f)
chk("сегодня разгон уже был — новые лимитки обычные", "boost" not in f["real"])
real_t = time.time
try:
    time.time = lambda: real_t() + 86400; V.bnf_positions = lambda: {}
    chk("назавтра (по Москве) разгон снова доступен, пока прошлая сделка открыта — нет", not V.dlm_boost_open())
    tr[0]["status"] = "CLOSED"
    chk("…а когда она закрыта — да", V.dlm_boost_open())
finally:
    time.time = real_t
# (5) the tally, the limit
t0 = tr[0]; t0["real"].update(e_real=1.0, x_real=1.012, filled=t0["real"].get("filled") or e["real"]["qty"]); t0["result"] = "WIN"
tg.clear(); V.dlm_boost_settle(); st = V.dlm_boost_status()
chk(f"тейк в итоге разгона: {st['net']:+.2f}$, сообщение «{(tg or [''])[0][:70]}…»", st["wins"] == 1 and st["net"] > 0 and "тейк" in tg[0])
def loss_trade(i):
    q = 20 / 0.06
    V._DLM["trades"].append({"id": f"x{i}", "symbol": "AAA_USDT", "side": 1, "direction": "LONG", "entry": 1.0, "exit": 0.94, "tp": 1.02, "status": "CLOSED", "result": "LOSS",
                             "t_in": int(now), "t_out": int(now) + i, "real": {"ex": "binance", "bsym": "AAAUSDT", "scl": 1.0, "filled": q, "boost": 20.0, "e_real": 1.0, "x_real": 0.94}})
for i in range(4): loss_trade(i)
tg.clear(); V.dlm_boost_settle(); st = V.dlm_boost_status()
chk(f"четыре стопа: итог {st['net']:+.2f}$, до лимита {st['left']}$ — ещё работает", V.DLM_BOOST and st["losses"] == 4)
loss_trade(9); loss_trade(10); tg.clear(); V.dlm_boost_settle(); st = V.dlm_boost_status()
chk(f"потери дошли до 5 ставок — разгон выключен сам и сказано: «{[m for m in tg if '⛔' in m][0][:90] if any('⛔' in m for m in tg) else ''}…»", not V.DLM_BOOST and st["off"] and any("выключен сам" in m for m in tg))
chk("выключенный разгон лимитки не берёт", not V.dlm_boost_open())
V.apply_settings({"dlm_boost": True}); st = V.dlm_boost_status()
chk(f"включили снова — лимит считается заново: до лимита {st['left']}$", V.DLM_BOOST and abs(st["left"] - 100) < 0.01 and not st["off"])
g = V.get_settings(); chk("настройки сохраняются", g["dlm_boost"] is True and g["dlm_boost_usd"] == 20 and g["dlm_boost_cap"] == 5)
V.apply_settings({"dlm_boost_usd": "abc", "dlm_boost_cap": 0}); chk("неверные значения не принимаются", V.DLM_BOOST_USD == 20 and V.DLM_BOOST_CAP == 5)
V.apply_settings({"dlm_boost_usd": 0}); chk("ставка 0 — разгон не работает", not V.dlm_boost_open())
V.apply_settings({"dlm_boost_usd": 20})
# (7) the page
import threading
threading.Thread(target=lambda: V.app.run(port=5131, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    bw = p.chromium.launch(executable_path="/opt/pw-browsers/chromium", args=["--no-sandbox"]); pg = bw.new_page(viewport={"width": 390, "height": 844})
    pe = []; pg.on("pageerror", lambda x: pe.append(str(x)))
    pg.goto("http://127.0.0.1:5131/"); pg.wait_for_timeout(2500); pg.click("#settingsBtn"); pg.wait_for_timeout(1500)
    grp = pg.evaluate("[...document.querySelectorAll('#settingsBody > details.settingsGroup')].map(d => d.querySelector('summary').textContent)")
    sec = pg.evaluate("(() => { const d = [...document.querySelectorAll('#settingsBody > details.settingsGroup')].find(d => d.textContent.includes('Режим разгона')); let e = d.previousElementSibling; while (e && !e.classList.contains('setSection')) e = e.previousElementSibling; return e && e.textContent; })()")
    pg.evaluate("[...document.querySelectorAll('#settingsBody > details.settingsGroup')].find(d => d.textContent.includes('Режим разгона')).open = true"); pg.wait_for_timeout(500)
    stt = pg.inner_text("#boostStatus"); vals = [pg.eval_on_selector("#setDlmBoost", "e => e.checked"), pg.input_value("#setDlmBoostUsd"), pg.input_value("#setDlmBoostCap")]
    chk(f"в настройках — раздел «{sec}», значения {vals}, статус «{stt[:70]}»", sec == "Торговля на бирже" and vals == [True, "20.0", "5.0"] or vals == [True, "20", "5"])
    chk(f"ошибок на странице нет {pe}", not pe)
    bw.close()
print("t_boost OK" if ok else "t_boost FAIL")
