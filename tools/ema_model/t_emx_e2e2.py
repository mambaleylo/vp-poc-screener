import json, random, types, time as _time, numpy as np, pandas as pd
from common import V as vp, load, D
LAB = json.load(open("/home/user/vp-poc-screener/vp_ema_model.json"))["lab"]
m = json.load(open("/home/user/vp-poc-screener/vp_ema_model.json"))
F = m["feats"]
d = pd.read_parquet(f"{D}/er_all.parquet", columns=["sym", "t", "j", "tf_s", "n_i", "lv"] + F + [LAB])
CS, AGG = {}, {}
def h1_of(sym):
    if sym not in CS:
        CS[sym] = load(sym)
        AGG[sym] = {"4h": vp._oc_agg(CS[sym], 4), "1d": vp._oc_agg(CS[sym], 24)}
    return CS[sym]
def closed(sym, tf, t, n):
    bars = h1_of(sym) if tf == "1h" else AGG[sym][tf]
    sec = {"1h": 3600, "4h": 14400, "1d": 86400}[tf]
    out = [c for c in bars if c["time"] + sec <= t]
    return out[-n:]
random.seed(11)
mm = dict(m); mm["thr"] = -1e9
ok = bad = miss = 0
worst = 0
for sym in ("SOLUSDT", "LINKUSDT", "DOGEUSDT", "AVAXUSDT"):
    sub = d[d.sym == sym]
    for _, row in sub.sample(12, random_state=3).iterrows():
        t = int(row.t)
        h1, h4, d1 = closed(sym, "1h", t, 1000), closed(sym, "4h", t, 1000), closed(sym, "1d", t, 3000)
        bh1, bh4, bd1 = closed("BTCUSDT", "1h", t, 1000), closed("BTCUSDT", "4h", t, 1000), closed("BTCUSDT", "1d", t, 3000)
        bt = {"cs": bh1, "t": [c["time"] for c in bh1], "S": vp.emx_series(bh1, bh4, bd1)}
        lvls = vp.emx_levels(sym, h1, h4, d1, t, mm, bt)
        hit = [a for a in lvls if a["tf"] == row.tf_s and a["n"] == row.n_i and a["side"] == row.side]
        x = [float(row[k]) for k in F]
        sc_r = sum(vp.zm_tree_pred(tt, x) for tt in m["models"]) / len(m["models"])
        if not hit:
            miss += 1
            print("MISS", sym, row.tf_s, row.n_i, row.side, "lv", row.lv, [ (a["tf"], a["n"], a["side"], round(a["lv"], 6)) for a in lvls][:6])
            continue
        a = hit[0]
        dl = abs(a["lv"] - row.lv) / row.lv
        ds = abs(a["score"] - sc_r)
        worst = max(worst, ds)
        if dl > 1e-4 or ds > 0.02:
            bad += 1
            print("DIFF", sym, row.tf_s, row.n_i, "lv", a["lv"], row.lv, "score", a["score"], round(sc_r, 3))
        else:
            ok += 1
print("ok", ok, "diff", bad, "miss", miss, "worst score diff", round(worst, 4))

# ---- the trade record: emx_fire + emx_settle on the 1h candles = the research's label
vp.send_telegram = lambda *a, **k: None
vp.emx_save = lambda: None
vp.notify_trade_result = lambda *a, **k: None
vp.get_candles_range = lambda sym, tf, a, b: [c for c in h1_of(sym.replace("_", "")) if a <= c["time"] <= b]
vp._EMX["model"] = m
ok2 = bad2 = 0
for sym in ("SOLUSDT", "LINKUSDT", "DOGEUSDT", "AVAXUSDT", "ETHUSDT"):
    sub = d[d.sym == sym]
    for _, row in sub.sample(15, random_state=5).iterrows():
        t = int(row.t)
        risk = row.lv * m["rule"]["stop_datr"] * row.datr / 100
        a = {"symbol": sym.replace("USDT", "_USDT"), "tf": row.tf_s, "n": int(row.n_i), "side": int(row.side), "lv": float(row.lv), "score": 0,
             "datr": float(row.datr), "sl": row.lv - row.side * risk, "tp": row.lv + row.side * m["rule"]["take_r"] * risk, "hour": t}
        vp._EMX["trades"] = []
        vp.emx_fire(a, t)
        vp.emx_settle(now=t + (m["rule"]["hold_h"] + 6) * 3600)
        tr = vp._EMX["trades"][0]
        if abs((tr["r"] or 0) - float(row[LAB])) < 0.01:
            ok2 += 1
        else:
            bad2 += 1
            print("R DIFF", sym, tr["result"], tr["r"], float(row[LAB]), "t", t, "data end", h1_of(sym)[-1]["time"])
print("trades ok", ok2, "diff", bad2)
