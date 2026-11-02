"""v0.99.768 — the models' age: the status by the schedule (P/R monthly from the 8th, the others yearly from 10 January), a
Telegram message per stale model at most every 3 days, /api/model_age; the ⚡ backtest list has the shifted 4h stream"""
import os, sys, json, time, tempfile, calendar
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import V
ok = True
def chk(nm, c):
    global ok
    print(f"{nm}: {'да' if c else 'НЕТ'}"); ok &= bool(c)
ts = lambda y, m, d: calendar.timegm((y, m, d, 12, 0, 0))
TT = {"vp_prv_model.json": ts(2026, 9, 30), "vp_dlm_model.json": ts(2025, 12, 29), "vp_smc_model.json": ts(2025, 12, 18),
      "vp_htf_model.json": ts(2025, 12, 18), "vp_cfl_model.json": ts(2025, 12, 18), "vp_ema_model.json": ts(2026, 9, 28)}
V._model_trained_to = lambda fn: TT[fn]
st = {x["file"]: x["stale"] for x in V.model_age_status(ts(2026, 11, 2))}
chk("2 ноября: ничего не устарело", not any(st.values()))
st = {x["file"]: x["stale"] for x in V.model_age_status(ts(2026, 11, 9))}
chk("9 ноября: P/R по сентябрь устарела, годовые нет", st["vp_prv_model.json"] and not any(v for k, v in st.items() if k != "vp_prv_model.json"))
TT["vp_prv_model.json"] = ts(2026, 10, 31)
st = {x["file"]: x["stale"] for x in V.model_age_status(ts(2026, 11, 9))}
chk("P/R по октябрь — свежая", not st["vp_prv_model.json"])
st = {x["file"]: x["stale"] for x in V.model_age_status(ts(2027, 1, 12))}
chk("12 января 2027: все годовые 2025-го и EMA по сентябрь 2026 — устарели", all(st[f] for f in ("vp_dlm_model.json", "vp_smc_model.json", "vp_htf_model.json", "vp_cfl_model.json", "vp_ema_model.json")))
st = {x["file"]: x["stale"] for x in V.model_age_status(ts(2027, 1, 7))}
chk("7 января 2027: годовые ещё не устарели (задача 5-го, ждёт «да»)", not any(st[f] for f in ("vp_dlm_model.json", "vp_smc_model.json")))
sent = []; V.send_telegram = lambda text, category=None: sent.append(text); V.MODEL_AGE_FILE = os.path.join(tempfile.mkdtemp(), "age.json")
V.model_age_tick(ts(2027, 1, 12)); n1 = len(sent)
V.model_age_tick(ts(2027, 1, 13)); n2 = len(sent)
V.model_age_tick(ts(2027, 1, 16)); n3 = len(sent)
chk("сообщения: по одному на устаревшую модель (12 января — все 6, P/R по октябрь тоже), повтор не раньше чем через 3 дня", n1 == 6 and n2 == 6 and n3 == 12 and "обучена по" in sent[0] and "RETRAIN.md" in sent[0])
d = V.app.test_client().get("/api/model_age", environ_base={"REMOTE_ADDR": "127.0.0.1"}).get_json()
chk("/api/model_age", len(d["models"]) == 6 and all("trained_to" in x for x in d["models"]))
L = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "vp_bt_trades.json")))["dlm"]
chk("бэктест ⚡: есть 4ч со сдвигом", sum(1 for t in L if t.get("st") == "wick4h_o2") > 500 and {t.get("st") for t in L} == {"wick4h", "close2h", "wick4h_o2"})
print("t_model_age OK" if ok else "t_model_age FAIL"); sys.exit(0 if ok else 1)
