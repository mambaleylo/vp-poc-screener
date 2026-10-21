"""parity: smc_core (pure Python, the bot's) vs lv_engine (numpy, the research) on the same Binance bars"""
import sys, math, time, bisect, calendar, numpy as np
exec(open("smc_core.py").read())
import lv_engine as LE
def bars(sym):
    T, O, H, L, C, V = LE.load_np(sym)
    return [{"time": int(t), "open": o, "high": h, "low": l, "close": c, "volume": v} for t, o, h, l, c, v in zip(T, O, H, L, C, V)]
def agg(h, sec):
    out = []
    for c in h:
        ps = c["time"] // sec * sec
        if not out or out[-1]["time"] != ps:
            out.append(dict(c, time=ps))
        else:
            b = out[-1]; b["high"] = max(b["high"], c["high"]); b["low"] = min(b["low"], c["low"]); b["close"] = c["close"]; b["volume"] += c["volume"]
    return out
B = bars("BTCUSDT"); BT = [c["time"] for c in B]; Bd = agg(B, 86400)
rng = np.random.default_rng(0)
tot = miss = 0; worst = np.zeros(29)
for sym in sys.argv[1:] or ["SOLUSDT", "DOGEUSDT", "1000PEPEUSDT"]:
    h = bars(sym); hT = [c["time"] for c in h]
    d = agg(h, 86400); h4 = agg(h, 14400)
    z = np.load(f"lv2/{sym}.npz")
    idx = np.flatnonzero((z["fam"] >= 33) & (z["t"] >= 1672531200))
    for i in rng.choice(idx, min(60, len(idx)), replace=False):
        t = int(z["t"][i]); J = bisect.bisect_left(hT, t)
        h1c = h[max(0, J - 1000):J]
        d1c = [c for c in d if c["time"] + 86400 <= t]
        h4c = [c for c in h4 if c["time"] + 14400 <= t][-1000:]
        bj = bisect.bisect_left(BT, t)
        cands = smc_candidates(h1c, h4c, d1c, B[max(0, bj - 1000):bj], [c for c in Bd if c["time"] + 86400 <= t], t)
        fam = SMC_FAMS[int(z["fam"][i])]; side = int(z["side"][i])
        m = [c for c in cands if c["fam"] == fam and c["side"] == side]
        tot += 1
        if not m or abs(m[0]["lv"] / float(z["lv"][i]) - 1) > 1e-6:
            miss += 1
            if miss <= 8: print("MISS", sym, t, fam, side, float(z["lv"][i]), [(c["fam"], c["side"], round(c["lv"], 8)) for c in cands if c["fam"] == fam])
            continue
        diff = np.abs(np.array(m[0]["f"]) - z["F"][i].astype(float))
        worst = np.maximum(worst, diff)
print("events", tot, "missed", miss)
for k, nm in enumerate(LE.FNAMES): print(f"{nm:10s} max|diff| {worst[k]:.5f}")
