"""v0.99.664 / 665: the bot's armed EMA levels (no 4h) carry the entry 0.2 daily ATR past the EMA, the stop / take from it"""
from common import V as vp, load
m = vp.emx_model(); assert m and m["rule"]["deep_datr"] == 0.2 and m["tfs"] == ["1d", "1w", "1M"] and m["ls_min_d24"] > 0, m and m.get("rule")
LSV = [None]
vp.binance_ls_d24 = lambda sym, t: LSV[0]
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
            assert a["tf"] != "4h", a; n += 1
print("levels ok", n)
cut = next(c for c in range(len(H) - 500, len(H) - 3500, -97) if [a for a in vp.emx_levels('ETH_USDT', H[c - 3000:c], agg(H[c - 3000:c], 4), agg(H[c - 3000:c], 24), H[c]['time'], m, {'cs': [x for x in B if x['time'] < H[c]['time']][-3000:], 't': [x['time'] for x in B if x['time'] < H[c]['time']][-3000:], 'S': vp.emx_series([x for x in B if x['time'] < H[c]['time']][-3000:], agg([x for x in B if x['time'] < H[c]['time']][-3000:], 4), agg([x for x in B if x['time'] < H[c]['time']][-3000:], 24))}) if a['side'] > 0]); h1 = H[cut - 3000:cut]; t_hour = H[cut]["time"]; b1 = [c for c in B if c["time"] < t_hour][-3000:]
bt = {"cs": b1, "t": [c["time"] for c in b1], "S": vp.emx_series(b1, agg(b1, 4), agg(b1, 24))}
LSV[0] = None; before = [a for a in vp.emx_levels("ETH_USDT", h1, agg(h1, 4), agg(h1, 24), t_hour, m, bt) if a["side"] > 0]
LSV[0] = -0.05; after = [a for a in vp.emx_levels("ETH_USDT", h1, agg(h1, 4), agg(h1, 24), t_hour, m, bt) if a["side"] > 0]
assert before and not after, (len(before), len(after))
print("crowd filter blocks: ok")
