"""v0.99.771 — 🧱 SMC take 4R: 1) the model file: the same trees and thr, rule.take_r 4, the armed level's take = lv + 4R;
2) the bot's hour settle fires a level touched EXACTLY (the candle's low = the level: what the new backtest counts);
3) the bot's smc_settle (the stop at a 4h close, the emergency 2x, the stop to the entry after a closed hour at +2R, take 4R,
96 h) walks 200 random trades of the new list (vp_bt_trades.json "smc", smc_export6.py) to the same R, kind and exit hour on
the lab's Binance candles (CANDLES: /home/user/ema211/data/1h)."""
import os, json, bisect, numpy as np
from common import V as vp
D1H = os.environ.get("CANDLES", "/home/user/ema211/data/1h")
ok = True
def chk(nm, c):
    global ok
    print(("OK  " if c else "FAIL") + " " + nm); ok &= bool(c)
vp.SMC_MODEL_FILE = "/home/user/vp-poc-screener/vp_smc_model.json"; vp._SMC["model"] = None
m = vp.smc_model()
chk("модель: ver 4, тейк 4R, порог прежний", m and m["ver"] == 4 and float(m["rule"]["take_r"]) == 4.0 and abs(float(m["thr"]) - 0.709599) < 1e-9)
H1 = {}
def load(sym):
    if sym not in H1:
        a = np.loadtxt(f"{D1H}/{sym}.csv", delimiter=",", ndmin=2); t = a[:, 0].astype(np.int64); keep = np.r_[True, np.diff(t) > 0]; a = a[keep]
        H1[sym] = ([{"time": int(r[0]), "open": r[1], "high": r[2], "low": r[3], "close": r[4]} for r in a], [int(x) for x in a[:, 0]])
    return H1[sym]
def rng_(sym, tf, a, b):
    h, ts = load(sym.replace("_", "")); return h[bisect.bisect_left(ts, a):bisect.bisect_right(ts, b)]
vp.get_candles_range = rng_; vp.binance_klines = lambda *a, **k: []; vp.mod_candles = lambda mod, sym, tf, a, b: rng_(sym, tf, a, b)
for f in ("send_telegram", "smc_save", "notify_trade_result"): setattr(vp, f, lambda *a, **k: None)
vp.AUTOTRADE_ENABLED_SMC = False
# 2) an exact touch fires at the hour's settle
h, _ = load("ETHUSDT"); c = h[-500]; hour = c["time"]; fired = []
vp._smc_can_open = lambda *a: True; real_fire = vp.smc_fire; vp.smc_fire = lambda a, t, *x, **k: fired.append(a["lv"])
vp._SMC["armed"] = [{"symbol": "ETH_USDT", "side": 1, "lv": c["low"]}, {"symbol": "ETH_USDT", "side": 1, "lv": c["low"] * 0.999}]
vp._SMC["armed_at"] = hour; vp._SMC["trades"] = []
vp.smc_settle(hour + 3601)
chk("касание ровно в уровень = сделка, не дошла = нет", fired == [c["low"]])
vp.smc_fire = real_fire
# 3) the walk of the new list
KR = {"stop": "LOSS", "hard": "LOSS", "be2": "BREAKEVEN", "take": "WIN", "time": "TIME_EXIT"}
L = [x for x in json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))["smc"] if os.path.exists(f"{D1H}/{x['s'].replace('_', '')}.csv")]
rng = np.random.default_rng(6); good = bad = 0
for x in [L[i] for i in rng.choice(len(L), min(200, len(L)), replace=False)]:
    tr = {"id": "x", "symbol": x["s"], "fam": x["lvl"], "side": x["d"], "direction": "LONG" if x["d"] > 0 else "SHORT", "entry": x["e"], "sl": x["sl"],
          "tp": x["tp"], "hour": x["t"], "hold": 96, "status": "OPEN", "real": False, "rv": 4, "ch": 4, "hs": x["hs"]}
    vp._SMC["trades"] = [tr]; vp._SMC["armed"] = []
    vp.smc_settle(x["x"] + 6 * 3600)
    g = tr["status"] == "CLOSED" and abs(tr["r"] - x["r"]) < 0.01 and tr["result"] == KR[x["k"]] and tr["t_out"] == x["x"]
    good += g; bad += not g
    if not g and bad <= 6: print("  ", x["s"], x["k"], x["r"], tr.get("result"), tr.get("r"), x["x"], tr.get("t_out"))
chk(f"сделки бота = список бэктеста: {good} из {good + bad}", bad == 0 and good >= 150)
print("t_smc_v6 OK" if ok else "t_smc_v6 FAIL")
