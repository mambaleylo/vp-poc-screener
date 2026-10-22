"""parity: dlm_core (pure Python, the bot's) vs s15_engine (numpy, the research) on the same Binance 15m bars"""
import sys, math, bisect, numpy as np
exec(open(sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].endswith(".py") else "dlm_core.py").read()) if not (len(sys.argv) > 1 and sys.argv[1] == "bot") else None
if len(sys.argv) > 1 and sys.argv[1] == "bot":
    from common import V
    dlm_candidates = V.dlm_candidates; DLM_FNAMES = V.DLM_FNAMES
import s15_engine as E
def bars(sym):
    T, O, H, L, C, Vv = E.load15(sym)
    return [{"time": int(t), "open": o, "high": h, "low": l, "close": c, "volume": v} for t, o, h, l, c, v in zip(T, O, H, L, C, Vv)]
def days(b):
    out = []
    for c in b:
        ps = c["time"] // 86400 * 86400
        if not out or out[-1]["time"] != ps: out.append(dict(c, time=ps))
        else:
            x = out[-1]; x["high"] = max(x["high"], c["high"]); x["low"] = min(x["low"], c["low"]); x["close"] = c["close"]
    return out
B = bars("BTCUSDT"); BT = [c["time"] for c in B]
rng = np.random.default_rng(3); tot = miss = 0; worst = np.zeros(28); bad_since = 0
for sym in ("SOLUSDT", "1000PEPEUSDT", "ARBUSDT"):
    b = bars(sym); bT = [c["time"] for c in b]; d = days(b)
    z = np.load(f"s15/{sym}.npz")
    idx = np.flatnonzero((z["fam"] == 0) & (z["t"] >= 1704067200))
    for k in rng.choice(idx, 40, replace=False):
        i = int(z["i"][k]); t = bT[i]
        w = b[max(0, i - 2999):i + 1]
        dd = [c for c in d if c["time"] + 86400 <= t]
        bj = bisect.bisect_right(BT, t)
        cs = dlm_candidates(w, dd, B[max(0, bj - 300):bj])
        m = [c for c in cs if c["side"] == int(z["side"][k])]
        tot += 1
        if not m: miss += 1; continue
        diff = np.abs(np.array(m[0]["f"]) - z["F"][k].astype(float))
        worst = np.maximum(worst, diff)
print("events", tot, "missed", miss)
for j, nm in enumerate(DLM_FNAMES): print(f"{nm:7s} {worst[j]:.5f}")
