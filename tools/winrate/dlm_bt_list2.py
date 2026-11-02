"""the ⚡ backtest list of the bot (vp_bt_trades.json["dlm"]) re-made on the streams the bot trades from v0.99.765 (the user:
"бэктест старый ещё что-ли? нету 4ч со сдвигом"): the lab's yearly walk-forward orders (every year scored by models trained on
the years before) of ⚡ 4h and 2h (_clr — what the header's money uses) and the shifted 4h (score >= 1.05 x the year's
threshold), the bot's exits; the bot's pool: by the fill hour, the first of a coin & side is the trade (any stream), busy
until its exit, at most 20 open a side; Gate names and prices (a Binance "1000" coin / 1000), "chk" = a coin the models never
trained on. usage: dlm_bt_list2.py [vp_bt_trades.json]"""
import sys, os, json, time, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlm_engine as DE
from common import V
OUT = sys.argv[1] if len(sys.argv) > 1 else "/home/user/vp-poc-screener/vp_bt_trades.json"; W = "/home/user/vp-lab-store/wf"
m = json.load(open("/home/user/vp-poc-screener/vp_dlm_model.json")); S = {s["name"]: s for s in m["streams"]}
GATE = set(V.RESEARCH_COINS_211)
def gate(bsym):
    b = bsym[:-4]
    if b.startswith("1000") and b[4:] + "_USDT" in GATE: return b[4:] + "_USDT", 1000.0
    return (b + "_USDT", 1.0) if b + "_USDT" in GATE else (None, None)
X = []
for st, f, k in (("wick4h", "allorders_wick4h_clr", 1.0), ("close2h", "allorders_close2h_clr", 1.0), ("wick4h_o2", "allorders_wick4h_o2", 1.05)):
    z = np.load(f"{W}/{f}.npz", allow_pickle=True); keep = z["filled"].astype(bool) & (z["score"] >= k * z["thr"]) & np.isfinite(z["R"]) & (z["t"] >= 1672531200)
    for i in np.flatnonzero(keep):
        X.append({"st": st, "coin": str(z["coin"][i]), "t0": int(z["t"][i]), "side": int(z["side"][i]), "lv": float(z["lv"][i]), "atr": float(z["atr"][i]),
                  "fill": float(z["fill"][i]), "t1h": int(z["t1h"][i]), "tout": int(z["tout"][i]), "R": float(z["R"][i]), "kind": int(z["kind"][i]),
                  "score": float(z["score"][i] / z["thr"][i]), "grp": str(z["grp"][i])})
X.sort(key=lambda x: (x["t1h"], -x["score"])); busy = {}; act = []; rows = []; skip = 0
for x in X:
    act = [a for a in act if a[0] > x["t1h"]]
    if busy.get((x["coin"], x["side"]), 0) > x["t1h"] or sum(1 for a in act if a[1] == x["side"]) >= 20: continue
    busy[(x["coin"], x["side"])] = x["tout"]; act.append((x["tout"], x["side"]))
    g, scl = gate(x["coin"])
    if not g: skip += 1; continue
    sm = S[x["st"]]; SOFT, HARD, TAKE = sm["stop_atr"], sm["hard_stop_atr"], sm["take_atr"]
    s = x["side"]; a = x["atr"]; e = x["fill"]; risk = SOFT * a
    q = (x["tout"] - 3600 - x["t1h"]) // 3600
    fee = (DE.FEE_IN + (DE.FEE_TAKE if x["kind"] == 1 else DE.FEE_OUT) + DE.FUND * (q + 1) / 24) * e
    xp = e + s * (x["R"] * risk + fee)
    f = lambda v: float(f"{v / scl:.6g}")
    rows.append({"s": g, "d": s, "c": "2h" if x["st"] == "close2h" else "4h", "st": x["st"], "t": x["t0"], "lv": f(x["lv"]), "e": f(e),
                 "sl": f(e - s * SOFT * a), "sl2": f(e - s * HARD * a), "tp": f(e + s * TAKE * a), "f": x["t1h"], "x": x["tout"], "xp": f(xp),
                 "r": round(x["R"], 3), "k": {1: "take", 3: "time"}.get(x["kind"], "stop"), "chk": x["grp"] != "train"})
L = json.load(open(OUT)); L["dlm"] = rows; L["made"] = int(time.time())
json.dump(L, open(OUT, "w"), separators=(",", ":"))
r = np.array([t["r"] for t in rows]); import collections
print(f"⚡ список: {len(rows)} сделок (без имени на Gate пропущено {skip}), {r.mean():+.3f}R, WR {(r > 0).mean()*100:.0f}%, по потокам {dict(collections.Counter(t['st'] for t in rows))}")
for Y in (2023, 2024, 2025, 2026):
    a_, b_ = int(np.datetime64(f"{Y}-01-01", 's').astype(int)), int(np.datetime64(f"{Y + 1}-01-01", 's').astype(int))
    y = np.array([t["r"] for t in rows if a_ <= t["t"] < b_]); print(f"  {Y}: {len(y)} сделок, {y.mean():+.3f}R, WR {(y > 0).mean()*100:.0f}%")
