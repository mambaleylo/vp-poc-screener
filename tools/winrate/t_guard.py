"""v0.99.786 — a bot position never left without a stop (the user: TURBO / HOME "позиция без стопа на бирже и без записи бота",
"почему само не может выставить?"): (1) ⚡'s state file keeps every armed limit (was: the last 400 orders — an older armed one
fell out, a restart forgot it); (2) a P/R / SMC / EMA / HTF / Классика record dropped (its stop and take cancelled) only when
Binance shows no position on two checks in a row — one empty answer no longer strips a live position; (3) the take-over: the
bot's own position with no stop and no record gets the emergency stop 3 ATR(4h) from the entry — a ⚡ one as a ⚡ trade again,
a market module's with a record; the price through it -> closed at the market; told once, not every 10 min; a manual
position never touched. Binance is a stub here: no real order anywhere"""
import time, json, os, tempfile
from common import V
ok = True
def chk(nm, c):
    global ok
    print(("OK  " if c else "FAIL") + " " + nm); ok &= bool(c)
d = tempfile.mkdtemp(prefix="vpguard_")
V.DLM_STATE_FILE = os.path.join(d, "dlm.json"); V.BNO_FILE = os.path.join(d, "bno.json")
sent = []; V.send_telegram = lambda t, category=None: sent.append((t, category))
logs = []; V.log_error = lambda m: logs.append(m)
# (1) the state file
now = time.time()
with V._dlm_lock:
    V._DLM["orders"] = [{"id": "armed_old", "symbol": "TURBO_USDT", "side": 1, "lv": 0.0007, "t0": now - 86400, "status": "OPEN", "real": {"id": "123", "ex": "binance"}}] + \
                       [{"id": f"o{i}", "symbol": "X_USDT", "side": 1, "lv": 1.0, "t0": now, "status": "SKIP", "real": None} for i in range(600)]
    V._DLM["trades"] = []
V.dlm_save(); saved = json.load(open(V.DLM_STATE_FILE))["orders"]
chk(f"в файле лимитка на бирже, хоть и старше 600 других ({len(saved)} заявок)", any(o["id"] == "armed_old" for o in saved) and len(saved) == 401)
chk("порядок заявок сохранён", saved[0]["id"] == "armed_old" and saved[-1]["id"] == "o599")
# (2) the record dropped only on two empty checks
cancelled = []; V._bno_cancel = lambda rec, kinds=("sl", "tp"): cancelled.append((rec["bsym"], kinds))
POS = {"v": {}}
V.bnf_positions = lambda: dict(POS["v"])
with V._bno_lock:
    V._BNO["pos"] = {"HOME_USDT": {"mode": "cfl", "bsym": "HOMEUSDT", "side": 1, "t": int(now) - 3600, "sl_id": "s1", "tp_id": "t1", "sl_px": 0.005, "tick": 1e-6, "step": 1}}
V.bno_tick()
chk("один пустой ответ Binance — запись цела, стоп и тейк не сняты", "HOME_USDT" in V._BNO["pos"] and not cancelled and V._BNO["pos"]["HOME_USDT"].get("miss_t"))
POS["v"] = {"HOMEUSDT": [{"amt": 100.0, "entry": 0.0054, "mark": 0.0054, "pside": "BOTH"}]}
V.bno_tick(); chk("позиция снова видна — отметка пропуска снята", "miss_t" not in V._BNO["pos"]["HOME_USDT"] and not cancelled)
POS["v"] = {}; V.bno_tick()
V._BNO["pos"]["HOME_USDT"]["miss_t"] = int(time.time()) - 61
V.bno_tick(); chk("нет позиции две проверки подряд (через минуту) — запись снята, её стоп и тейк тоже", "HOME_USDT" not in V._BNO["pos"] and cancelled == [("HOMEUSDT", ("sl", "tp"))])
# (3) the take-over of a naked position
V.BINANCE_API_KEY, V.BINANCE_API_SECRET, V.DLM_BINANCE, V.AUTOTRADE_DRY_RUN = "k", "s", True, False
ORD = {"TURBOUSDT": "vpdlm1762650000000", "HOMEUSDT": "vpcfl1762650000000", "AINUSDT": "android_abc123"}
placed, market = [], []
class Err(V.BinanceError): pass
TRIG = {"through": False}
def place_cond(bsym, s, kind, px, dual):
    if TRIG["through"]:
        raise V.BinanceError(-2021, "Order would immediately trigger.")
    placed.append((bsym, kind, float(px))); return ("algo", f"id{len(placed)}")
def req(method, path, params=None):
    if path == "/fapi/v1/allOrders":
        return [{"status": "FILLED", "side": "BUY", "reduceOnly": False, "closePosition": False, "executedQty": "100", "updateTime": 1, "clientOrderId": ORD[params["symbol"]]}]
    if path == "/fapi/v1/openOrders":
        return []
    if path == "/fapi/v1/openAlgoOrders":
        return []
    if method == "POST" and path == "/fapi/v1/order":
        market.append(params); return {"orderId": 9}
    return {}
V.bnf_req = req; V.bnf_place_cond = place_cond; V.bnf_dual = lambda: False
V.bnf_symbols = lambda: {b: {"tick": 1e-9, "step": 1.0, "min_qty": 1.0, "min_notional": 5} for b in ("TURBOUSDT", "HOMEUSDT", "AINUSDT")}
ATR = {"TURBO_USDT": 1.61e-5, "HOME_USDT": 1.53e-4, "AIN_USDT": 0.01}
V._dlm_atr_at = lambda sym, t, bs=14400: ATR.get(sym)
V.RESEARCH_COINS_211 = tuple(V.RESEARCH_COINS_211) + ("TURBO_USDT", "HOME_USDT", "AIN_USDT")
V._dlm_bn_exits_real = V._dlm_bn_exits
POS["v"] = {"TURBOUSDT": [{"amt": 100000.0, "entry": 0.000696426, "mark": 0.00069, "pside": "BOTH"}],
            "HOMEUSDT": [{"amt": 2000.0, "entry": 0.0054, "mark": 0.0053, "pside": "BOTH"}],
            "AINUSDT": [{"amt": 10.0, "entry": 0.5, "mark": 0.5, "pside": "BOTH"}]}
with V._dlm_lock:
    V._DLM["orders"] = []; V._DLM["trades"] = []
with V._bno_lock:
    V._BNO["pos"] = {}
V._ADOPT["who"] = {}; V._ADOPT["owner"] = {}
lines = V.dlm_bn_adopt(time.time())
print("   " + "\n   ".join(lines))
tl = next((l for l in lines if "TURBOUSDT" in l), ""); hl = next((l for l in lines if "HOMEUSDT" in l), "")
tt = next((t for t in V._DLM["trades"] if t["symbol"] == "TURBO_USDT"), None)
sl_t = next((p for b, k, p in placed if b == "TURBOUSDT" and k == "STOP_MARKET"), None)
want = (tt.get("hsl") or tt["sl"]) if tt else None
chk(f"TURBO (лимитка ⚡): снова сделка ⚡, стоп на бирже {sl_t} = стоп правила ⚡ {want} ({abs(0.000696426 - (want or 0)) / 1.61e-5:.2f} ATR)",
    tt and tt["real"].get("guard") and sl_t and abs(sl_t - want) < 2e-9 and "🛡" in tl and "снова ведёт" in tl and "по правилу ⚡" in tl)
chk("TURBO: тейк ⚡ тоже выставлен (лимиткой)", any(p.get("type") == "LIMIT" and p.get("symbol") == "TURBOUSDT" for p in market))
sl_h = next((p for b, k, p in placed if b == "HOMEUSDT" and k == "STOP_MARKET"), None)
chk(f"HOME (Классика по рынку): аварийный стоп {sl_h} = вход − 3 ATR ({0.0054 - 3 * 1.53e-4:.6f}), запись модуля «cfl»",
    sl_h and abs(sl_h - (0.0054 - 3 * 1.53e-4)) < 2e-9 and V._BNO["pos"]["HOME_USDT"]["mode"] == "cfl" and V._BNO["pos"]["HOME_USDT"]["sl_id"] and "Классика" in hl)
chk("ручная позиция AIN не тронута и не в сообщении", not any(b == "AINUSDT" for b, _, _ in placed) and not any("AIN" in l for l in lines))
n_before = len(placed)
lines2 = V.dlm_bn_adopt(time.time() + 600)
chk(f"через 10 минут — тишина: позиции уже в записях ({lines2})", not lines2 and len(placed) == n_before)
# the price already through the stop
TRIG["through"] = True; market.clear()
with V._bno_lock:
    V._BNO["pos"] = {}
with V._dlm_lock:
    V._DLM["trades"] = []
POS["v"] = {"HOMEUSDT": [{"amt": 2000.0, "entry": 0.0054, "mark": 0.0049, "pside": "BOTH"}]}
lines3 = V.dlm_bn_adopt(time.time() + 1200)
print("   " + "\n   ".join(lines3))
chk("цена уже за аварийным стопом — закрыта по рынку (как сработал бы стоп)", any(p.get("type") == "MARKET" and p.get("symbol") == "HOMEUSDT" for p in market) and "закрыта по рынку" in lines3[0])
print("t_guard OK" if ok else "t_guard FAIL")
