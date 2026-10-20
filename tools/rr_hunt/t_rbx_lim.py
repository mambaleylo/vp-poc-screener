"""v0.99.663: the bot's rbx_settle with the limit entry (0.2 ATR better than the entry bar's open, 3 bars) on Binance
candles = the research's list (rb_part3.py): the same fill, exit kind, time and R; no-fill signals stay out"""
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
for f in ("send_telegram", "rbx_save", "notify_trade_result"): setattr(vp, f, lambda *a, **k: None)
vp.AUTOTRADE_ENABLED_RBX = False
KR = {"fail": "FAILED", "stop": "LOSS", "be": "BREAKEVEN", "trend": "TREND_END", "time": "TIME_EXIT", "take": "WIN"}
rng = np.random.default_rng(5)
rb = [x for x in json.load(open("rbx_bt_v663.json")) if not x["s"].startswith("1000") and load(x["s"].replace("_", ""))]
ok = bad = 0
for x in [rb[i] for i in rng.choice(len(rb), 200, replace=False)]:
    cfg = vp.RBX_CHARTS[x["c"]]; s = x["d"]; risk = abs(x["e"] - x["sl"])
    tr = {"id": "x", "symbol": x["s"], "side": s, "direction": "LONG" if s > 0 else "SHORT", "chart": x["c"], "hrs": cfg["hrs"], "hold": cfg["hold"],
          "day": x["t"], "risk": risk, "entry": None, "sl": None, "px": x["e"], "half": False, "part": True, "part_r": vp.RBX_PART_R,
          "part_f": vp.RBX_PART_F, "status": "PENDING", "real": False, "lim_atr": vp.RBX_LIM_ATR, "wait": vp.RBX_LIM_WAIT,
          "lvl": x["hh"] if s > 0 else x["ll"], "fail_k": x.get("fk", 0)}
    vp._RBX["trades"] = [tr]
    vp.rbx_settle(now=x["x"] + 2 * cfg["hrs"] * 3600)
    good = (tr["status"] == "CLOSED" and tr["r"] is not None and abs(tr["r"] - x["r"]) < 0.01 and tr["result"] == KR[x["k"]]
            and tr["t_out"] == x["x"] and abs(tr["entry"] - x["e"]) < 1e-9 * max(1, x["e"]) + 1e-12 and tr["kf_t"] == x["f"])
    ok += good; bad += not good
    if not good: print("rbx", x["s"], x["c"], x["k"], x["r"], x["e"], x["f"], "|", tr.get("result"), tr.get("r"), tr.get("entry"), tr.get("kf_t"), x["x"], tr.get("t_out"))
print("rbx ok", ok, "bad", bad)
