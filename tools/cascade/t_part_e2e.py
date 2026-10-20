"""v0.99.654: the bot's rbx_settle / cas_settle with the partial take on Binance candles = the research's backtest lists
(rb_part.py "rbx", cas_part.py "cas"): the same exit kind, time and R"""
import json, bisect, numpy as np
from common import V as vp, load
H1 = {}
def h1_of(sym):
    if sym not in H1:
        h = load(sym); H1[sym] = (h, [c["time"] for c in h], vp._oc_agg(h, 24))
    return H1[sym]
def rng_(sym, tf, a, b):
    h, ts, d1 = h1_of(sym.replace("_", ""))
    if tf == "1d": return [c for c in d1 if a <= c["time"] <= b]
    return h[bisect.bisect_left(ts, a):bisect.bisect_right(ts, b)]
vp.get_candles_range = rng_
for f in ("send_telegram", "rbx_save", "cas_save", "notify_trade_result"): setattr(vp, f, lambda *a, **k: None)
vp.AUTOTRADE_ENABLED_RBX = vp.AUTOTRADE_ENABLED_CAS = False
KR = {"stop": "LOSS", "be": "BREAKEVEN", "trend": "TREND_END", "time": "TIME_EXIT", "take": "WIN"}
rng = np.random.default_rng(3)
rb = [x for x in json.load(open("rbx_bt_v654.json")) if not x["s"].startswith("1000") and load(x["s"].replace("_", ""))]
ok = bad = 0
for x in [rb[i] for i in rng.choice(len(rb), 150, replace=False)]:
    cfg = vp.RBX_CHARTS[x["c"]]; s = x["d"]; risk = abs(x["e"] - x["sl"])
    tr = {"id": "x", "symbol": x["s"], "side": s, "direction": "LONG" if s > 0 else "SHORT", "chart": x["c"], "hrs": cfg["hrs"], "hold": cfg["hold"],
          "day": x["t"], "risk": risk, "entry": None, "sl": x["e"] - s * risk, "px": x["e"], "half": False, "part": True, "part_r": vp.RBX_PART_R,
          "part_f": vp.RBX_PART_F, "status": "OPEN", "real": False}
    vp._RBX["trades"] = [tr]
    vp.rbx_settle(now=x["x"] + 2 * cfg["hrs"] * 3600)
    good = tr["status"] == "CLOSED" and abs(tr["r"] - x["r"]) < 0.01 and tr["result"] == KR[x["k"]] and tr["t_out"] == x["x"]
    ok += good; bad += not good
    if not good: print("rbx", x["s"], x["c"], x["k"], x["r"], tr.get("result"), tr.get("r"), x["x"], tr.get("t_out"))
print("rbx ok", ok, "bad", bad)
cs_ = [x for x in json.load(open("cas_bt_v654.json")) if not x["s"].startswith("1000") and load(x["s"].replace("_", ""))]
ok = bad = 0
for x in [cs_[i] for i in rng.choice(len(cs_), 150, replace=False)]:
    s = x["d"]; risk = abs(x["e"] - x["sl"])
    tr = {"id": "x", "symbol": x["s"], "side": s, "tf": 1, "direction": "LONG" if s > 0 else "SHORT", "hour": x["t"], "score": 1, "risk": risk, "entry": None,
          "sl": x["sl"], "tp": None, "px": x["e"], "hold": 48, "take_r": 2.5, "part_r": 0.7, "part_f": 0.33, "until": x["t"] + 48 * 3600, "status": "OPEN", "real": False}
    vp._CAS["trades"] = [tr]
    vp.cas_settle(x["t"] + 60 * 3600)
    good = tr["status"] == "CLOSED" and abs(tr["r"] - x["r"]) < 0.01 and tr["result"] == KR[x["k"]] and tr["t_out"] == x["x"] and tr["part"] == x["part"]
    ok += good; bad += not good
    if not good: print("cas", x["s"], x["k"], x["r"], tr.get("result"), tr.get("r"), x["x"], tr.get("t_out"))
print("cas ok", ok, "bad", bad)
