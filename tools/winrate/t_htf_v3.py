"""v0.99.773 — 📏 HTF reach 2.5: 1) the model file: the same models and thresholds, rule.reach_datr 2.5; 2) the bot's arm filter
keeps a level 2.5 daily ATR away (the 1.5 one dropped it); 3) the bot's htf_settle (the stop at a 1d close, the emergency 3x,
take 3R, 96 h) walks 200 random trades of the new list (vp_bt_trades.json "htf", htf_export3.py) to the same R, kind and exit
hour on the lab's Binance candles (CANDLES: /home/user/ema211/data/1h)."""
import os, json, bisect, numpy as np
from common import V as vp
D1H = os.environ.get("CANDLES", "/home/user/ema211/data/1h")
ok = True
def chk(nm, c):
    global ok
    print(("OK  " if c else "FAIL") + " " + nm); ok &= bool(c)
vp.HTF_MODEL_FILE = "/home/user/vp-poc-screener/vp_htf_model.json"; vp._HTF["model"] = None
m = vp.htf_model()
chk("модель: досягаемость 2.5, модели и пороги прежние", m and float(m["rule"]["reach_datr"]) == 2.5 and abs(float(m["thr_o"]) - 0.6777573532639909) < 1e-9
    and abs(float(m["thr_n"]) - 1.0733757545199634) < 1e-9)
# 2) the arm filter on a level 2 dATR away
H1 = {}
def load(sym):
    if sym not in H1:
        a = np.loadtxt(f"{D1H}/{sym}.csv", delimiter=",", ndmin=2); t = a[:, 0].astype(np.int64); keep = np.r_[True, np.diff(t) > 0]; a = a[keep]
        H1[sym] = ([{"time": int(r[0]), "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]} for r in a], [int(x) for x in a[:, 0]])
    return H1[sym]
h, _ = load("ETHUSDT"); t_hour = h[-500]["time"] + 3600; px = h[-500]["close"]; d = 2.0
fake = [{"side": 1, "lv": px * (1 - d * 3.0 / 100), "datr": 3.0, "fam": 1, "f": [0.0] * len(vp.SMC_FNAMES)}]
vp.smc_candidates = lambda *a, **k: fake
vp.htf_scores = lambda m_, f: (9.0, 9.0); vp.htf_pick = lambda m_, so, sn: "on"
vp._zm_closed = lambda sym, tf, sec, n, now: [c for c in load("ETHUSDT")[0] if c["time"] + sec <= now][-n:] if tf == "1h" else [{"time": 0, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]
vp._research_syms = lambda coins, mode=None: ["ETH_USDT"]; vp.limit_touched_since = lambda *a: False
for f in ("send_telegram", "htf_save", "notify_trade_result", "heartbeat"): setattr(vp, f, lambda *a, **k: None)
import time as _t
_real = _t.time; vp.time.time = lambda: t_hour + 60
try:
    vp.htf_arm()
finally:
    vp.time.time = _real
chk("уровень в 2 дн. ATR от цены взят в работу (при 1.5 был бы отброшен)", any(abs(a["lv"] - fake[0]["lv"]) < 1e-9 for a in vp._HTF["armed"]))
# 3) the walk of the new list
def rng_(sym, tf, a, b):
    hh, ts = load(sym.replace("_", "")); return hh[bisect.bisect_left(ts, a):bisect.bisect_right(ts, b)]
vp.get_candles_range = rng_; vp.mod_candles = lambda mod, sym, tf, a, b: rng_(sym, tf, a, b)
vp.AUTOTRADE_ENABLED_HTF = False
KR = {"stop": "LOSS", "hard": "LOSS", "take": "WIN", "time": "TIME_EXIT"}
L = [x for x in json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))["htf"] if os.path.exists(f"{D1H}/{x['s'].replace('_', '')}.csv")]
rng = np.random.default_rng(3); good = bad = 0
for x in [L[i] for i in rng.choice(len(L), min(200, len(L)), replace=False)]:
    tr = {"id": "x", "symbol": x["s"], "fam": x["lvl"], "side": 1, "direction": "LONG", "entry": x["e"], "sl": x["sl"], "tp": x["tp"], "hour": x["t"],
          "hold": 96, "status": "OPEN", "real": False, "ch": 24, "hs": x["hs"]}
    vp._HTF["trades"] = [tr]; vp._HTF["armed"] = []
    vp.htf_settle(x["x"] + 26 * 3600)
    g = tr["status"] == "CLOSED" and abs(tr["r"] - x["r"]) < 0.01 and tr["result"] == KR[x["k"]] and tr["t_out"] == x["x"]
    good += g; bad += not g
    if not g and bad <= 6: print("  ", x["s"], x["k"], x["r"], tr.get("result"), tr.get("r"), x["x"], tr.get("t_out"))
chk(f"сделки бота = список бэктеста: {good} из {good + bad}", bad == 0 and good >= 150)
print("t_htf_v3 OK" if ok else "t_htf_v3 FAIL")
