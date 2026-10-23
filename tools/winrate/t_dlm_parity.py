"""parity (v0.99.687): the bot's dlm_candidates4 (pure Python) vs s20h4_engine (numpy, the research) on the same Binance
4h bars: every sampled wick1 event of the research must come out of the bot with the same 33 features (the engine's 28,
s24_feat.py's 5 daily ones)"""
import sys, bisect, numpy as np
from common import V
import os; os.environ["TFH"] = "4"
import s23_engine as E
def bars(sym):
    T, O, H, L, C, Vv = E.load15(sym)
    return [{"time": int(t), "open": o, "high": h, "low": l, "close": c, "volume": v} for t, o, h, l, c, v in zip(T, O, H, L, C, Vv)]
B = bars("BTCUSDT"); BT = [c["time"] for c in B]
rng = np.random.default_rng(3); tot = miss = extra = 0; worst = np.zeros(33)
for sym in ("SOLUSDT", "1000PEPEUSDT", "ARBUSDT", "DOGEUSDT"):
    b = bars(sym); bT = [c["time"] for c in b]
    z = np.load(f"s23_4h/{sym}.npz"); F2 = np.load(f"s24_4h/{sym}.npz")["F2"][:, [0, 1, 2, 5, 8]]
    F33 = np.full((len(z["t"]), 33), np.nan); F33[:, :28] = z["F"]; F33[z["fam"] == 2, 28:] = F2
    idx = np.flatnonzero((z["fam"] == 2) & (z["t"] >= 1704067200))
    for k in rng.choice(idx, 40, replace=False):
        i = int(z["i"][k])
        w = b[max(0, i - 2999):i + 1]
        bj = bisect.bisect_right(BT, bT[i])
        cs = V.dlm_candidates4(w, B[max(0, bj - 3000):bj], min_bars=0)
        m = [c for c in cs if c["side"] == int(z["side"][k])]
        tot += 1
        if not m: miss += 1; continue
        worst = np.maximum(worst, np.abs(np.array(m[0]["f"]) - F33[k].astype(np.float32).astype(float)))
    # no event the research did not have: bars with no wick1 event of a side -> the bot gives none either
    ev = {(int(i_), int(s_)) for i_, s_, f_ in zip(z["i"], z["side"], z["fam"]) if f_ == 2}
    for i in rng.choice(np.arange(3000, len(b)), 30, replace=False):
        w = b[max(0, i - 2999):i + 1]; bj = bisect.bisect_right(BT, bT[i])
        for c in V.dlm_candidates4(w, B[max(0, bj - 3000):bj], min_bars=0):
            lv = c["lv"]; s = c["side"]
            filled = any(((b[j]["low"] <= lv) if s > 0 else (b[j]["high"] >= lv)) for j in range(i + 1, min(i + 5, len(b))))
            if filled and (int(i), s) not in ev: extra += 1
print("events", tot, "missed", miss, "extra", extra)
for j, nm in enumerate(V.DLM_FNAMES4): print(f"{nm:7s} {worst[j]:.6f}")
ok = miss == 0 and extra == 0 and worst.max() < 1e-3
print("OK" if ok else "FAIL"); sys.exit(0 if ok else 1)
