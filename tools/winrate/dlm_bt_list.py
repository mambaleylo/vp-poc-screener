"""the ⚡ backtest list of the bot (vp_bt_trades.json["dlm"]) from the walk-forward pool (dlm_pool's rules on the yearly
models' choices, the bot's coins 2023-2026) walked with the model file's exits; Gate names and prices (a Binance "1000"
coin / 1000), "chk" = a coin the models never trained on. usage: dlm_bt_list.py [vp_bt_trades.json]"""
import sys, os, json, time, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlm_exits as DX, dlm_engine as DE
from common import V
OUT = sys.argv[1] if len(sys.argv) > 1 else "/home/user/vp-poc-screener/vp_bt_trades.json"
m = json.load(open("/home/user/vp-poc-screener/vp_dlm_model.json")); S = {s["name"]: s for s in m["streams"]}
assert len({(s["take_atr"], s["stop_atr"], s["hard_stop_atr"]) for s in S.values()}) == 1
st0 = next(iter(S.values())); TAKE, SOFT, HARD = st0["take_atr"], st0["stop_atr"], st0["hard_stop_atr"]
GATE = set(V.RESEARCH_COINS_211)
def gate(bsym):
    b = bsym[:-4]
    if b.startswith("1000") and b[4:] + "_USDT" in GATE: return b[4:] + "_USDT", 1000.0
    return (b + "_USDT", 1.0) if b + "_USDT" in GATE else (None, None)
Pw = DX.walk(DX.pool_lv(), take=TAKE, soft=SOFT, hard=HARD)
rows = []; skip = 0
for x in sorted(Pw, key=lambda x: (x["t1h"], -x["score"])):
    g, scl = gate(x["coin"])
    if not g: skip += 1; continue
    s = x["side"]; a = x["atr"]; e = x["fill"]; risk = SOFT * a
    q = (x["tout"] - 3600 - x["t1h"]) // 3600
    fee = (DE.FEE_IN + (DE.FEE_TAKE if x["kind"] == 1 else DE.FEE_OUT) + DE.FUND * (q + 1) / 24) * e
    xp = e + s * (x["R"] * risk + fee)
    f = lambda v: float(f"{v / scl:.6g}")
    rows.append({"s": g, "d": s, "c": "4h" if x["st"] == "wick4h" else "2h", "st": x["st"], "t": int(x["t0"]), "lv": f(x["lv"]), "e": f(e),
                 "sl": f(e - s * SOFT * a), "sl2": f(e - s * HARD * a), "tp": f(e + s * TAKE * a), "f": int(x["t1h"]), "x": int(x["tout"]), "xp": f(xp),
                 "r": round(x["R"], 3), "k": {1: "take", 3: "time"}.get(x["kind"], "stop"), "chk": x["grp"] != "train"})
L = json.load(open(OUT)); L["dlm"] = rows; L["made"] = int(time.time())
json.dump(L, open(OUT, "w"), separators=(",", ":"))
r = np.array([t["r"] for t in rows])
print(f"⚡ list: {len(rows)} trades (skipped {skip} without a Gate name), {r.mean():+.3f}R, WR {(r > 0).mean()*100:.0f}%, take {TAKE} stop {SOFT} hard {HARD}")
