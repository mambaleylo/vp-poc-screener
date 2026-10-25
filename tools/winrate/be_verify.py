"""v0.99.719 audit: every SMC backtest trade walked by the BOT's own _cs_walk on the 1h candles — without the break-even
(must give the list's R) and with SMC_BE_R (vs be_heat2.json)"""
import json, os, numpy as np
from common import V
OLD = json.load(open("../bt_old.json"))["smc"]; BE = json.load(open("be_heat2.json"))["2.0"]["smc"]
NORM = lambda x: x.replace("_USDT", "").replace("USDT", "").replace("1000", "")
def h1(sym):
    b = sym.replace("_USDT", "")
    for c, scl in ((b + "USDT", 1.0), ("1000" + b + "USDT", 1000.0)):
        f = f"data/1h/{c}.csv"
        if os.path.exists(f):
            a = np.loadtxt(f, delimiter=",", ndmin=2); return [{"time": int(r[0]), "open": r[1] / scl, "high": r[2] / scl, "low": r[3] / scl, "close": r[4] / scl} for r in a]
    return None
same0 = diff0 = 0; agree = dis = 0; r0s = []; r2s = []; mism = []
for t in OLD:
    cs = h1(t["s"])
    if cs is None: continue
    cs = [c for c in cs if c["time"] >= t["t"]]
    s, fill, sl, tp = t["d"], t["e"], t["sl"], t["tp"]; risk = abs(fill - sl)
    hx = abs(fill - t["hs"]) / risk
    for pr, acc in ((0.0, r0s), (V.SMC_BE_R, r2s)):
        res = V._cs_walk(cs, s, fill, sl, tp, 96, 4, hx, pr)
        if not res: acc.append(None); continue
        kind, ex, k, took = res
        acc.append(round(s * (ex - fill) / risk - (V.SMC_FEE + V.SMC_FUND * (k + 1) / 24) * fill / risk, 3))
    if r0s[-1] is not None and abs(r0s[-1] - t["r"]) < 0.02: same0 += 1
    else: diff0 += 1
    key = f"{NORM(t['s'])}_{t['t']}_{round(t['r'], 2)}"
    want = BE[key][1] if key in BE else t["r"]
    if r2s[-1] is not None and abs(r2s[-1] - want) < 0.02: agree += 1
    else: dis += 1; mism.append((t["s"], t["t"], t["r"], want, r2s[-1], r0s[-1]))
print(f"the bot's walk without the break-even = the list's R: {same0} of {same0 + diff0}")
print(f"the bot's walk with it = the research (be_heat2): {agree} of {agree + dis}")
print("the mismatches:", mism[:8])
ok = [i for i, (a, b) in enumerate(zip(r0s, r2s)) if a is not None and b is not None]
print(f"mean R on the same trades: without {np.mean([r0s[i] for i in ok]):+.3f} · with {np.mean([r2s[i] for i in ok]):+.3f} · changed {sum(1 for i in ok if abs(r0s[i] - r2s[i]) > 1e-9)}")
