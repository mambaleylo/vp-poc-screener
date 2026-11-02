"""v0.99.769 — EMA v13: 1) the model file has no crowd filter and a crowd that did not add longs no longer blocks a level;
2) the bot's hour settle fires a level touched EXACTLY (the candle's low = the limit, no 0.1% margin — what the new backtest
counts); 3) the bot's emx_settle (the v12 exits: the stop at a 4h close, the emergency one, 1/3 at +1R then breakeven,
take 4R, 72 h) walks 200 random trades of the new backtest list (vp_bt_trades.json "emx", ema_export13.py) to the same
R, the same kind and the same exit hour, on the lab's Binance candles."""
import json, bisect, numpy as np
from common import V as vp, load
ok = True
def chk(nm, c):
    global ok
    print(("OK  " if c else "FAIL") + " " + nm); ok &= bool(c)
vp.EMX_MODEL_FILE = "/home/user/vp-poc-screener/vp_ema_model.json"
m = vp.emx_model()
chk("модель v12, без фильтра толпы", m and m["ver"] == 12 and m.get("ls_min_d24") is None and m["research"]["years"].get("2026"))
H1 = {}
def rng_(sym, tf, a, b):
    s = sym.replace("_", "")
    if s not in H1: h = load(s); H1[s] = (h, [c["time"] for c in h])
    h, ts = H1[s]; return h[bisect.bisect_left(ts, a):bisect.bisect_right(ts, b)]
vp.get_candles_range = rng_; vp.binance_klines = lambda *a, **k: []; vp.mod_candles = lambda mod, sym, tf, a, b: rng_(sym, tf, a, b)
for f in ("send_telegram", "emx_save", "notify_trade_result"): setattr(vp, f, lambda *a, **k: None)
vp.AUTOTRADE_ENABLED_EMW = False
# 1) the crowd: levels with the crowd against = levels without data
LSV = [None]; vp.binance_ls_d24 = lambda sym, t: LSV[0]; vp.emx_pass = lambda *a, **k: True
agg = lambda h, n: vp._oc_agg(h, n); B = load("BTCUSDT"); H = load("ETHUSDT"); same = n_lv = 0
for cut in range(len(H) - 3000, len(H) - 100, 499):
    h1 = H[cut - 3000:cut]; t_hour = H[cut]["time"]; b1 = [c for c in B if c["time"] < t_hour][-3000:]
    bt = {"cs": b1, "t": [c["time"] for c in b1], "S": vp.emx_series(b1, agg(b1, 4), agg(b1, 24))}
    LSV[0] = None; a0 = vp.emx_levels("ETH_USDT", h1, agg(h1, 4), agg(h1, 24), t_hour, m, bt)
    LSV[0] = -0.05; a1 = vp.emx_levels("ETH_USDT", h1, agg(h1, 4), agg(h1, 24), t_hour, m, bt)
    n_lv += len(a0); same += [(a["lv"], a["side"]) for a in a0] == [(a["lv"], a["side"]) for a in a1]
chk(f"толпа против — уровни те же ({n_lv} уровней)", same == len(range(len(H) - 3000, len(H) - 100, 499)) and n_lv > 0)
# 2) an exact touch fires at the hour's settle
c = H[-500]; hour = c["time"]; fired = []
vp._emx_can_open = lambda *a: True; vp.emx_fire = lambda a, t, *x, **k: fired.append(a["lv"])
vp._EMX["armed"] = [{"symbol": "ETH_USDT", "side": 1, "lv": c["low"]}, {"symbol": "ETH_USDT", "side": 1, "lv": c["low"] * 0.999}]
vp._EMX["armed_at"] = hour; vp._EMX["trades"] = []
vp.emx_settle(hour + 3601)
chk("касание ровно в лимитку = сделка, не дошла = нет", fired == [c["low"]])
# 3) the walk of the new list (no level is armed: emx_fire is not called)
KR = {"stop": "LOSS", "hard": "LOSS", "be": "BREAKEVEN", "take": "WIN", "time": "TIME_EXIT"}
L = [x for x in json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))["emx"] if not x["s"].startswith("1000") and load(x["s"].replace("_", ""))]
rng = np.random.default_rng(13); good = bad = 0
for x in [L[i] for i in rng.choice(len(L), min(200, len(L)), replace=False)]:
    tr = {"id": "x", "symbol": x["s"], "side": x["d"], "direction": "LONG" if x["d"] > 0 else "SHORT", "tf": x["tf"], "n": x["n"], "entry": x["e"], "sl": x["sl"], "tp": x["tp"],
          "hour": x["t"], "hold": 72, "status": "OPEN", "real": False, "sel": True, "part_r": 1.0, "part_f": 0.33, "ch": 4, "hs": x["hs"]}
    vp._EMX["trades"] = [tr]; vp._EMX["armed"] = []
    vp.emx_settle(x["x"] + 6 * 3600)
    g = tr["status"] == "CLOSED" and abs(tr["r"] - x["r"]) < 0.01 and tr["result"] == KR[x["k"]] and tr["t_out"] == x["x"]
    good += g; bad += not g
    if not g and bad <= 6: print("  ", x["s"], x["k"], x["r"], tr.get("result"), tr.get("r"), x["x"], tr.get("t_out"))
chk(f"сделки бота = список бэктеста: {good} из {good + bad}", bad == 0 and good >= 150)
print("t_emx_v13 OK" if ok else "t_emx_v13 FAIL")
