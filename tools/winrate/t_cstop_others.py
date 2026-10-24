"""v0.99.700 — SMC and EMA: the stop at a 4h close beyond the stop (the emergency one on the exchange at 2x): (1) the bot's
own fire + settle re-make trades of the backtest lists of every exit kind (take, the close stop, the emergency stop, time,
EMA's breakeven) on Binance's 1h candles, R equal; (2) the real path: the order's stop = the emergency one, the risk x2
(the loss at the close stop = the module's risk %), a close stop -> the position closed at the market"""
import sys, os, json, bisect
from common import V, load
B = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))
def bname(gs):
    b = gs.replace("_USDT", "")
    for c, scl in ((b + "USDT", 1.0), ("1000" + b + "USDT", 1000.0)):
        if os.path.exists(f"{os.path.dirname(os.path.abspath(sys.modules['common'].__file__))}/data/1h/{c}.csv"):
            return c, scl
    return None, None
H = {}
def rng_(sym, tf, a, b):
    if sym not in H:
        c, scl = bname(sym); cs = load(c) or []
        H[sym] = ([dict(x, open=x["open"] / scl, high=x["high"] / scl, low=x["low"] / scl, close=x["close"] / scl) for x in cs], [x["time"] for x in cs])
    cs, ts_ = H[sym]; return cs[bisect.bisect_left(ts_, a):bisect.bisect_right(ts_, b)]
V.get_candles_range = rng_
V.binance_klines = lambda *a, **k: []
for f in ("send_telegram", "smc_save", "emx_save", "notify_trade_result"): setattr(V, f, lambda *a, **k: None)
closed, orders = [], []
V.close_position_for_mode = lambda mode, sym, d: (closed.append((mode, sym)), {"ok": True})[1]
V.execute_autotrade = lambda mode, sym, d, px, sl, tp, extra=None, risk_pct_override=None, **k: (orders.append((mode, sym, sl, risk_pct_override, (extra or {}).get("kx"))), {"status": "OPENED"})[1]
ok = True
V.smc_model(); V.emx_model()
for mod, kinds in (("smc", ("take", "stop", "hard", "time")), ("emx", ("take", "stop", "hard", "time", "be"))):
    lst = [t for t in B[mod] if bname(t["s"])[0] and t["t"] > 1735689600]
    picks = [t for k in kinds for t in [x for x in lst if x["k"] == k][:2]]
    good = 0
    for t in picks:
        s = t["d"]; now = t["x"] + 7200
        a = {"symbol": t["s"], "side": s, "lv": t["e"], "sl": t["sl"], "tp": t["tp"], "score": 1.0, "hour": t["t"]}
        if mod == "smc":
            V._SMC["trades"] = []; a["fam"] = t.get("lvl", "fvg4_bull")
            V.AUTOTRADE_ENABLED_SMC = False; V.smc_fire(a, t["t"]); V.smc_settle(now); tr = V._SMC["trades"][0]
        else:
            V._EMX["trades"] = []; a.update({"tf": t.get("tf", "1d"), "n": t.get("n", 20), "ema": t.get("ema", t["e"])})
            V.AUTOTRADE_ENABLED_EMW = False; V.emx_fire(a, t["t"]); V.emx_settle(now); tr = V._EMX["trades"][0]
        same = tr["status"] == "CLOSED" and abs((tr["r"] or 0) - t["r"]) < 0.002
        good += same
        print(f"   {mod} {t['s']:14s} {t['k']:5s} R bot {tr.get('r')} vs list {t['r']} {'✓' if same else '✗'}")
    print(f"({mod}) {good}/{len(picks)} re-made"); ok &= good == len(picks) and len(picks) >= 6
# (2) the real path: SMC on, a trade whose 4h close goes beyond the stop
t = next(x for x in B["smc"] if x["k"] == "stop" and bname(x["s"])[0] and x["t"] > 1735689600)
V._SMC["trades"] = []; V.AUTOTRADE_ENABLED_SMC = True; V.MODULE_RISK_PCT["smc"] = 0.5; orders.clear(); closed.clear()
a = {"symbol": t["s"], "side": t["d"], "lv": t["e"], "sl": t["sl"], "tp": t["tp"], "score": 1.0, "hour": t["t"], "fam": t.get("lvl", "fvg4_bull")}
V.smc_fire(a, t["t"], live_px=t["e"]); V.smc_settle(t["x"] + 7200)
o = orders[0] if orders else (None,) * 5
real_ok = (abs(o[2] - t["hs"]) < 1e-9 * max(1, abs(t["hs"])) and abs(o[3] - 1.0) < 1e-9 and o[4] == 2.0 and closed == [("smc", t["s"])]
           and V._SMC["trades"][0]["result"] == "LOSS")
print("(real) the exchange stop = the emergency one", o[2], "vs", t["hs"], "· risk 0.5% x2 =", o[3], "· a 4h close beyond -> closed at the market", closed, real_ok)
ok &= real_ok
print("ALL OK" if ok else "FAILED"); sys.exit(0 if ok else 1)
