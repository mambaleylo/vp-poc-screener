"""v0.99.662: the bot's prx_settle with the limit entry on Binance candles = pr_export_lim.py's list"""
import json, bisect, numpy as np
from common import V as vp, load
H1 = {}
def rng_(sym, tf, a, b):
    s = sym.replace("_", "")
    if s not in H1: h = load(s); H1[s] = (h, [c["time"] for c in h])
    h, ts = H1[s]; return h[bisect.bisect_left(ts, a):bisect.bisect_right(ts, b)]
vp.get_candles_range = rng_
for f in ("send_telegram", "prx_save", "notify_trade_result"): setattr(vp, f, lambda *a, **k: None)
vp.AUTOTRADE_ENABLED_PRV = False
KR = {"hard": "HARD_STOP", "stop": "STOP_CLOSE", "take": "WIN", "time": "TIME_EXIT"}
bt = [x for x in json.load(open("prv_bt_v662.json")) if not x["s"].startswith("1000") and load(x["s"].replace("_", ""))]
ok = bad = 0
for x in bt:
    s = x["d"]; a = s * (x["e"] - x["hs"]) / 6.0
    tr = {"id": "x", "symbol": x["s"], "side": s, "tf": 1, "direction": "LONG" if s > 0 else "SHORT", "hour": x["t"], "score": 1, "risk": 6 * a, "soft": 3 * a,
          "entry": None, "sl": None, "tp": None, "hs": None, "px": x["e"], "hold": 48, "take_r": 1.5, "until": x["t"] + 51 * 3600, "status": "PENDING",
          "real": False, "atr": a, "lim_atr": 0.3, "wait": 3, "lv": x["lv"]}
    vp._PRX["trades"] = [tr]
    vp.prx_settle(x["x"] + 6 * 3600)
    good = tr["status"] == "CLOSED" and abs(tr["r"] - x["r"]) < 0.01 and tr["result"] == KR[x["k"]] and tr["t_out"] == x["x"]
    ok += good; bad += not good
    if not good: print(x["s"], x["k"], x["r"], tr.get("result"), tr.get("r"), x["x"], tr.get("t_out"))
print("prv ok", ok, "bad", bad)
