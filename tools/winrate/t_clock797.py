"""v0.99.797 — the user's log (16–18.11): the phone's clock jumps (Gate: 105 s behind -> "gap between request Timestamp and server
time exceeds 60"; Binance: -1021 on the positions' read and on two ⚡ limits, RED and HBAR) and a trade's chart of a coin Gate dropped
(BROCCOLI714: 400). (1) Binance: -1021 -> the clock synced now and the request once more (it was refused: nothing done); twice -> the
error; the clock synced every 5 min (was 30); (2) Gate: its own clock offset in the signature, synced every 5 min; REQUEST_EXPIRED
-> synced, once more; (3) the chart: Gate's error -> Binance's candles; (4) a -2013 the bot settles itself is a warning"""
import time, json
from common import V
ok = True
def chk(nm, c):
    global ok
    print(("OK  " if c else "FAIL") + " " + nm); ok &= bool(c)
errs = []; V.log_error = lambda m: errs.append(str(m))
class R:
    def __init__(self, code, j): self.status_code, self._j = code, j; self.text = json.dumps(j); self.ok = code == 200
    def json(self): return self._j
    def raise_for_status(self): pass
# (1) Binance
V.BINANCE_API_KEY, V.BINANCE_API_SECRET = "k" * 20, "s" * 20
seq = []; syncs = []
def b_req(method, url, headers=None, timeout=None, **k):
    seq.append(url); return answers.pop(0)
V.requests.request = b_req
def b_get(url, timeout=None, **k):
    syncs.append(url); return R(200, {"serverTime": int(time.time() * 1000) + 105000})
_get = V.requests.get; V.requests.get = b_get
V._BNF["synced"] = time.time()
answers = [R(400, {"code": -1021, "msg": "Timestamp for this request is outside of the recvWindow."}), R(200, [{"ok": 1}])]
out = V.bnf_req("GET", "/fapi/v3/positionRisk")
chk(f"Binance -1021: часы сверены сразу, запрос повторён один раз и прошёл ({len(seq)} запроса, сверок {len(syncs)})", out == [{"ok": 1}] and len(seq) == 2 and len(syncs) == 1)
chk(f"смещение часов учтено: {V._BNF['offset'] / 1000:.0f} с", abs(V._BNF["offset"] / 1000 - 105) < 2)
answers = [R(400, {"code": -1021, "msg": "x"}), R(400, {"code": -1021, "msg": "x"})]; seq.clear()
try: V.bnf_req("GET", "/fapi/v3/positionRisk"); raised = False
except V.BinanceError as e: raised = e.code == -1021
chk("повтор снова -1021 — ошибка, без бесконечных повторов", raised and len(seq) == 2)
chk("часы Binance сверяются раз в 5 минут (было 30)", V.BNF_SYNC_SEC == 300)
# (2) Gate
V._current_credentials = lambda: ("gk", "gs", "main")
gate_ts = []
def g_req(method, url, headers=None, data=None, timeout=None, **k):
    gate_ts.append(float(headers["Timestamp"])); return g_answers.pop(0)
V.requests.request = g_req
V.requests.get = lambda url, timeout=None, **k: R(200, {"server_time": int((time.time() + 105) * 1000)})
V._GATE_T.update(offset=0.0, synced=time.time())   # the old, wrong offset (the phone's own clock)
g_answers = [R(403, {"label": "REQUEST_EXPIRED", "message": "gap between request Timestamp and server time exceeds 60"}), R(200, [{"id": 1}])]
out = V.gate_signed_request("GET", "/futures/usdt/orders", "status=open")
chk(f"Gate REQUEST_EXPIRED: часы Gate сверены, запрос повторён и прошёл; метка второго запроса на {gate_ts[1] - gate_ts[0]:.0f} с впереди", out == [{"id": 1}]
    and len(gate_ts) == 2 and abs(gate_ts[1] - gate_ts[0] - 105) < 2)
g_answers = [R(403, {"label": "REQUEST_EXPIRED"}), R(403, {"label": "REQUEST_EXPIRED"})]; gate_ts.clear()
try: V.gate_signed_request("GET", "/futures/usdt/orders"); raised = False
except Exception as e: raised = "403" in str(e)
chk("снова REQUEST_EXPIRED — ошибка, без бесконечных повторов", raised and len(gate_ts) == 2)
V._GATE_T.update(synced=time.time() - 400); V.gate_now()
chk("часы Gate сверяются раз в 5 минут сами", time.time() - V._GATE_T["synced"] < 5)
V.requests.get = _get
# (3) the chart of a coin Gate dropped
def gone(*a, **k): raise V.requests.exceptions.HTTPError("400 Client Error: Bad Request: CONTRACT_NOT_FOUND")
V.get_candles_range = gone
h = int(time.time()) // 3600 * 3600
V.binance_klines = lambda sym, iv, a, b: [{"time": h - 3600 * i, "open": 1, "high": 1, "low": 1, "close": 1} for i in range(5, 0, -1)]
with V.app.test_client() as c:
    j = c.get(f"/api/btchart/BROCCOLI714_USDT?c=1h&t={h - 7200}").get_json()
chk(f"график сделки по монете, которой больше нет на Gate: свечи Binance ({j.get('src')}, {len(j.get('bars') or [])} шт.), без ошибки", j.get("src") == "binance" and j.get("bars") and not j.get("error"))
# (4) the level
chk("«-2013 Order does not exist» у лимитки ⚡ — предупреждение, не ошибка", V.log_level("dlm binance order TAO_USDT: Binance -2013: Order does not exist.") == "warn")
# (5) no free margin: the ⚡ order waits, not "no trade" (the user: "вдруг она освободилась")
V.DLM_BINANCE = True; V.AUTOTRADE_DRY_RUN = False; V.DLM_BOOST = False
V.bn_map = lambda sym: (sym.replace("_", ""), 1.0)
V.bnf_symbols = lambda: {"AAAUSDT": {"tick": 0.0001, "step": 0.1, "min_qty": 0.1, "min_notional": 5.0, "ok": True}}
V.bnf_positions = lambda: {}; V.bnf_dual = lambda: False; V.bnf_tiers = lambda b: [(1e9, 0.005, 50)]; V._BNF["lev_cap"] = 20
ACC = {"equity": 1000.0, "free": 0.5}; V.bnf_account = lambda: dict(ACC)
V.dlm_osc_mult = lambda *a, **k: 1.0; V.dlm_load_mult = lambda: 1.0; V._dlm_bn_pre_exits = lambda o_, sl: None
V.bn_margin_mode = lambda b: "CROSSED"; V.bn_heat_cap = lambda risk, eq, mode=None: (risk, None)
posts = []
def fq(method, path, params=None, **k):
    if path == "/fapi/v1/order": posts.append(params); return {"orderId": 7}
    return {}
V.bnf_req = fq; V._DLM["model"] = dict(V.dlm_model() or {})
o = {"id": "dlm_AAA_USDT_1_1", "symbol": "AAA_USDT", "side": 1, "lv": 1.0, "atr": 0.02, "score": 0.9, "bs": 14400, "st": "wick4h", "t0": int(time.time()), "until": time.time() + 40000, "status": "OPEN", "real": None}
V.dlm_bn_place(o)
chk(f"нет свободной маржи — лимитка не «пропущена», а ждёт: «{o.get('hold', '')[:60]}…»", o["real"] is None and "ждёт" in o.get("hold", "") and not posts)
ACC["free"] = 900.0; V.dlm_bn_place(o)
chk("маржа освободилась — лимитка встала на биржу", (o.get("real") or {}).get("id") == "7" and posts)
print("t_clock797 OK" if ok else "t_clock797 FAIL")
