"""v0.99.685 — 🪜 the risk / withdrawal ladder: the risk by the account size, the risk used at a Binance placement, the
Telegram reminder at 5 K, the withdrawal seen only by a transfer out (a stop's drop is not one), the burnt account ->
the start again, the "rebase" button, both ladders replayed on the real trades, the settings and the UI"""
import sys, time
from common import V
msgs = []
V.send_telegram = lambda m, category=None: msgs.append(m)
V.dlm_save = lambda: None
V.log_error = lambda m: print("   log:", m)
res = {}
V.apply_settings({"dlm_ladder": True, "dlm_ladder_mode": "grow", "dlm_ladder_base": 100, "risk_pct_dlm": 5})
res["settings"] = V.DLM_LADDER and V.get_settings()["dlm_ladder_mode"] == "grow" and V.get_settings()["dlm_ladder_base"] == 100
res["risk by size"] = (V.dlm_risk(120) == 50 and V.dlm_risk(400) == 30 and V.dlm_risk(1500) == 15)
V.apply_settings({"dlm_ladder": False}); off = V.dlm_risk(120) == 5; V.apply_settings({"dlm_ladder": True})
res["off -> the field"] = off
# the placement takes the ladder's risk
V.DLM_BINANCE = True; V.BINANCE_API_KEY = V.BINANCE_API_SECRET = "x"
V.bn_map = lambda s: ("AAAUSDT", 1.0)
V.bnf_symbols = lambda: {"AAAUSDT": {"tick": 0.001, "step": 0.1, "min_qty": 0.1, "min_notional": 5.0, "ok": True}}
V.bnf_positions = lambda: {}
V.bnf_dual = lambda: False
V.bnf_tiers = lambda b: [(5000.0, 0.01, 50)]
V.bnf_account = lambda: {"wallet": 400.0, "equity": 400.0, "free": 400.0, "upnl": 0.0}
sent = []
def req(method, path, params=None, **k):
    sent.append((method, path, params)); return {"orderId": 1}
V.bnf_req = req
V._DLM["model"] = {"rule": {"stop_atr": 2.0}}
o = {"id": "x", "symbol": "AAA_USDT", "side": 1, "lv": 10.0, "atr": 0.1, "score": 0.1, "t0": 0, "until": time.time() + 999, "status": "OPEN", "real": None}
V.dlm_bn_place(o)
res["placement risk 30% at $400"] = o["real"]["risk"] == 30.0
# the ladder tick
V._DLM.update({"ladder": {}, "trades": []})
OUT = [0.0]; V.bnf_transfers_out = lambda since: OUT[0]
V.dlm_ladder_tick(100.0); a = not msgs and V._DLM["ladder"]["K"] == 100
V.dlm_ladder_tick(520.0); b = len(msgs) == 1 and "$210" in msgs[0] and "$310" in msgs[0]
V.dlm_ladder_tick(530.0); c = len(msgs) == 1                                    # reminded once
V.dlm_ladder_tick(300.0); d = V._DLM["ladder"]["K"] == 100 and len(msgs) == 1     # a stop's drop, no transfer: not a withdrawal
OUT[0] = 215.0; V.dlm_ladder_tick(310.0); e = V._DLM["ladder"]["K"] == 310 and "замечен" in msgs[-1]
p = V.dlm_ladder_plan(310.0); f = p["target"] == 1550 and p["risk"] == 30
res["reminder / withdrawal / not a stop"] = a and b and c and d and e and f
V.dlm_ladder_tick(5.0); g = V._DLM["ladder"]["K"] == 100 and "сгорел" in msgs[-1]; n = len(msgs)
V.dlm_ladder_tick(4.0); h = len(msgs) == n
res["burnt -> start again, once"] = g and h
V.dlm_equity = lambda: 150.0
r = V.app.test_client().post("/api/dlm/ladder", json={"action": "rebase"}).get_json()
res["rebase button"] = r["ok"] and V._DLM["ladder"]["K"] == 150
rep = V.dlm_ladder_replay([0.24] * 300, "grow", 100.0); rep2 = V.dlm_ladder_replay([0.24] * 300, "safe", 100.0)
rep3 = V.dlm_ladder_replay([-1.0] * 5, "grow", 100.0)
res["replay"] = rep["withdrawals"] > 0 and rep["net"] > 0 and rep2["withdrawals"] > 0 and rep3["deposited"] > 100
# UI
V._DLM["trades"] = [{"id": "t", "symbol": "AAA_USDT", "side": 1, "direction": "LONG", "entry": 1, "lv": 1, "atr": 0.01, "sl": 0.98, "tp": 1.005, "score": 0.1, "t0": 0,
                     "fbar": 0, "t_in": time.time() - 999, "until": 0, "status": "CLOSED", "result": "WIN", "r": 0.24, "exit": 1.005, "t_out": time.time(), "real": {"ex": "binance"}, "rv": 1}]
st = V.app.test_client().get("/api/dlm/status").get_json()
html = V.app.test_client().get("/").get_data(as_text=True)
res["status + ui"] = st["ladder"]["on"] and st["ladder_cmp"]["grow"]["deposited"] == 100 and "setDlmLadder" in html and "dlmLadderRebase" in html
print(" · ".join(f"{k} {v}" for k, v in res.items()))
ok = all(res.values()); print("ALL OK" if ok else "FAILED"); sys.exit(0 if ok else 1)
