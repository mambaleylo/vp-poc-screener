"""v0.99.664: the bot's armed EMA levels carry the entry 0.2 daily ATR past the EMA, the stop / take from it"""
from common import V as vp, load
m = vp.emx_model(); assert m and m["rule"]["deep_datr"] == 0.2, m and m.get("rule")
vp.emx_pass = lambda *a, **k: True
agg = lambda h, n: vp._oc_agg(h, n)
B = load("BTCUSDT"); n = 0
for sym in ("ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"):
    H = load(sym)
    for cut in range(len(H) - 3000, len(H) - 100, 397):
        h1 = H[cut - 3000:cut]; t_hour = H[cut]["time"]; b1 = [c for c in B if c["time"] < t_hour][-3000:]
        bt = {"cs": b1, "t": [c["time"] for c in b1], "S": vp.emx_series(b1, agg(b1, 4), agg(b1, 24))}
        for a in vp.emx_levels(sym[:-4] + "_USDT", h1, agg(h1, 4), agg(h1, 24), t_hour, m, bt):
            s, d = a["side"], a["datr"]
            assert abs(a["lv"] - a["ema"] * (1 - s * 0.2 * d / 100)) < 1e-9 * a["ema"], a
            assert abs((a["lv"] - a["sl"]) * s - a["lv"] * 0.75 * d / 100) < 1e-9 * a["lv"], a
            assert abs((a["tp"] - a["lv"]) * s - 4 * (a["lv"] - a["sl"]) * s) < 1e-9 * a["lv"], a
            n += 1
print("levels ok", n)
