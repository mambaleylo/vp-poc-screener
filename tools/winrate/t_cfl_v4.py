"""v0.99.776 — 🔄 Классика: (1) the model file: 210 coins, the threshold of the 127, the drought rule 14 d / q 0.99; (2) the scan
(the data mocked): a candidate under the main threshold but over the drought one opens only after 14 idle days, and after
one opens in the scan the next drought-only ones do not; a 210-only coin's score never enters the threshold's store;
(3) the risk 2% and the own open-risk room: Классика's positions do not count in the others' room and the others' not in
its 25%; (4) the real trades on by default under a new setting key"""
import time, json
from common import V
ok = True
def chk(nm, c):
    global ok
    print(("OK  " if c else "FAIL") + " " + nm); ok &= bool(c)
V.CFL_MODEL_FILE = "/home/user/vp-poc-screener/vp_cfl_model.json"; V._CFL["model"] = None
m = V.cfl_model()
chk("модель: 210 монет, порог по 127, мягкий порог 14 дн / q 0.99", m and len(m["coins"]) == 210 and len(m["thr_coins"]) == 127
    and set(m["thr_coins"]) <= set(m["coins"]) and m["rule"]["drought_d"] == 14 and m["rule"]["drought_q"] == 0.99)
# (2) the scan with mocked data: 3 coins — A (a trained coin), B (a trained coin), X (one of the 83)
A, B, X = m["thr_coins"][0], m["thr_coins"][1], next(c for c in m["coins"] if c not in set(m["thr_coins"]))
SC = {A: 0.80, B: 0.70, X: 0.75}   # the main threshold 0.9, the drought one 0.6: A, B, X under the main, over the drought
V.cfl_threshold = lambda m_, t, q=None: 0.6 if q is not None else 0.9
V.cfl_klines = lambda bsym, iv, n: ([1], [1.0], [1.0], [1.0], [1.0], [1.0])
V.cfl_tf_events_at = lambda h4, d1, t: [1]
V.cfl_oi = lambda b: None; V.cfl_funding = lambda b: None; V.heartbeat = lambda *a, **k: None; V.time.sleep = lambda s: None
V._CFL["first"] = {c: 0 for c in m["coins"]}
V.cfl_coin_events = lambda bsym, t_close, m_, *a: [(0, -1, [bsym, 0, 4.0])] if bsym in SC else []   # S -1: the trade a long
V.cfl_score = lambda m_, f: SC[f[0]]
added = []; V.cfl_add_score = lambda day, sc: added.append(sc)
opened = []
def fake_open(c, t_close, m_):
    opened.append(c["bsym"]); V._CFL["trades"].append({"t_in": t_close, "status": "OPEN", "bsym": c["bsym"], "side": 1}); return True
V.cfl_open = fake_open
t0 = 1793404800   # 2026-11-01 00:00
V._CFL["trades"] = [{"t_in": t0 - 20 * 86400, "status": "CLOSED", "bsym": "Z", "side": 1}]   # the last trade 20 days ago
V.cfl_scan(t0)
chk(f"простой 20 дн: открыта одна сделка по мягкому порогу, следующие — нет ({opened})", opened == [A])
chk("в хранилище порога только 127 обученных монет (X не попала)", sorted(added) == sorted([SC[A], SC[B]]))
opened.clear(); V._CFL["trades"] = [{"t_in": t0 - 5 * 86400, "status": "CLOSED", "bsym": "Z", "side": 1}]   # 5 days ago
V.cfl_scan(t0)
chk("простой 5 дн: по мягкому порогу ничего", opened == [])
SC[B] = 0.95; opened.clear(); V.cfl_scan(t0)
chk("выше основного порога — открывается всегда", opened == [B])
# (3) the risk and the room
chk("риск Классики по умолчанию 2%", V.BN_OTHERS_RISK["cfl"] == 2.0 and V.BN_CFL_HEAT == 0.35)
V._BNO["pos"] = {"AAA_USDT": {"mode": "cfl", "qty": 10.0, "entry": 10.0, "sl_px": 9.0, "side": 1},     # $10 at risk
                 "BBB_USDT": {"mode": "smc", "qty": 30.0, "entry": 10.0, "sl_px": 9.0, "side": 1}}     # $30 at risk
with V._dlm_lock: V._DLM["trades"] = []; V._DLM["orders"] = []
chk("риск открытых: Классика отдельно ($10), остальные без неё ($30)", abs(V.bn_heat(100.0, "cfl") - 10) < 1e-9 and abs(V.bn_heat(100.0) - 30) < 1e-9)
r1, w1 = V.bn_heat_cap(2.0, 100.0, "cfl"); r2, w2 = V.bn_heat_cap(2.0, 100.0, "cfl")
V._BNO["pos"]["CCC_USDT"] = {"mode": "cfl", "qty": 24.0, "entry": 10.0, "sl_px": 9.0, "side": 1}   # Классика $34 of its $35 (v0.99.777)
r3, w3 = V.bn_heat_cap(2.0, 100.0, "cfl"); r4, w4 = V.bn_heat_cap(2.0, 100.0, "smc")
chk(f"своя комната 35%: свободно — полный риск, $1 места — урезано ({r3}), остальным не мешает ({r4})", r1 == 2.0 and abs(r3 - 1.0) < 1e-9 and r4 == 2.0)
# (4) the switch
chk("автоторговля Классики по умолчанию вкл, новый ключ настройки", V.AUTOTRADE_ENABLED_CFL is True and "autotrade_cfl2" in V.SETTINGS_KEYS and "autotrade_cfl" not in V.SETTINGS_KEYS)
print("t_cfl_v4 OK" if ok else "t_cfl_v4 FAIL")
