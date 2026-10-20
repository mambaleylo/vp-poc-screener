"""the bot's cas_settle on Binance candles vs the research's backtest trades (cas_bt.json): same exit, same R"""
import json, numpy as np
from common import V, load
bt = json.load(open("cas_bt.json"))
rev = {}
def sym_of(gs):
    b = gs[:-5]
    for cand in (b + "USDT", "1000" + b + "USDT"):
        if load(cand): return cand, (1000.0 if cand.startswith("1000") else 1.0)
CACHE = {}
def candles(symbol, tf, start, end):
    if symbol not in CACHE: CACHE[symbol] = sym_of(symbol)
    s, scl = CACHE[symbol]
    return [{k: (c[k] / scl if k in ("open", "high", "low", "close") else c[k]) for k in ("time", "open", "high", "low", "close")} for c in load(s) if start <= c["time"] <= end]
V.get_candles_range = candles
V.notify_trade_result = lambda *a, **k: None
V.cas_save = lambda: None
rng = np.random.default_rng(2); ok = bad = 0
for t in [bt[i] for i in rng.choice(len(bt), 80, replace=False)]:
    tr = {"id": "x", "symbol": t["s"], "side": t["d"], "tf": 1, "direction": "LONG" if t["d"] > 0 else "SHORT", "hour": t["t"], "score": 1, "risk": None,
          "entry": None, "sl": t["sl"], "tp": None, "px": t["e"], "hold": 48, "take_r": 2.0, "until": t["t"] + 48 * 3600, "status": "OPEN", "real": False}
    V._CAS["trades"] = [tr]
    V.cas_settle(t["t"] + 60 * 3600)
    good = tr["status"] == "CLOSED" and abs(tr["r"] - t["r"]) < 0.01 and tr["t_out"] == t["x"]
    ok += good; bad += not good
    if not good: print(t["s"], t["k"], t["r"], tr.get("result"), tr.get("r"), t["x"], tr.get("t_out"))
print("ok", ok, "bad", bad)
