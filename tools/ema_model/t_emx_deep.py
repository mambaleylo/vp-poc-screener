"""v0.99.664: the bot's emx_settle with the partial take on Binance candles = ema_export6.py (the entry 0.2 daily ATR past the EMA)'s backtest list"""
import json, bisect, numpy as np
from common import V as vp, load
H1 = {}
def rng_(sym, tf, a, b):
    s = sym.replace("_", "")
    if s not in H1: h = load(s); H1[s] = (h, [c["time"] for c in h])
    h, ts = H1[s]; return h[bisect.bisect_left(ts, a):bisect.bisect_right(ts, b)]
vp.get_candles_range = rng_
for f in ("send_telegram", "emx_save", "notify_trade_result"): setattr(vp, f, lambda *a, **k: None)
vp.AUTOTRADE_ENABLED_EMW = False
KR = {"stop": "LOSS", "be": "BREAKEVEN", "take": "WIN", "time": "TIME_EXIT"}
bt = [x for x in json.load(open("emx_bt_v664.json")) if not x["s"].startswith("1000") and load(x["s"].replace("_", ""))]
rng = np.random.default_rng(4); ok = bad = 0
for x in [bt[i] for i in rng.choice(len(bt), 150, replace=False)]:
    tr = {"id": "x", "symbol": x["s"], "side": x["d"], "direction": "LONG" if x["d"] > 0 else "SHORT", "tf": x["tf"], "n": x["n"], "entry": x["e"], "sl": x["sl"], "tp": x["tp"],
          "hour": x["t"], "hold": 72, "status": "OPEN", "real": False, "sel": True, "part_r": 1.0, "part_f": 0.33}
    vp._EMX["trades"] = [tr]; vp._EMX["armed"] = []
    vp.emx_settle(x["x"] + 6 * 3600)
    good = tr["status"] == "CLOSED" and abs(tr["r"] - x["r"]) < 0.01 and tr["result"] == KR[x["k"]] and tr["t_out"] == x["x"]
    ok += good; bad += not good
    if not good: print(x["s"], x["k"], x["r"], tr.get("result"), tr.get("r"), x["x"], tr.get("t_out"))
print("emx ok", ok, "bad", bad)
