"""parity (v0.99.687; v0.99.689 — both streams: 4h wick = s23 w1, 2h close-2ATR = s21h2 d2): the bot's dlm_candidates4 (pure Python) vs the engines (numpy, the research) on the same Binance
4h bars: every sampled wick1 event of the research must come out of the bot with the same 33 features (the engine's 28,
s24_feat.py's 5 daily ones)"""
import sys, bisect, numpy as np
from common import V
import os, importlib
STREAMS = [("s23_4h", "s23_engine", 4, 2, {"name": "wick4h", "anchor": "wick", "depth_atr": 1.0, "fam": 2.0}),
           ("s21h2", "s21h2_engine", 2, 0, {"name": "close2h", "anchor": "close", "depth_atr": 2.0, "fam": 0.0})]
def bars(sym, E):
    T, O, H, L, C, Vv = E.load15(sym)
    return [{"time": int(t), "open": o, "high": h, "low": l, "close": c, "volume": v} for t, o, h, l, c, v in zip(T, O, H, L, C, Vv)]
rng = np.random.default_rng(3); tot = miss = extra = 0; worst = np.zeros(33)
for (dr, eng, tfh, fam, ST), sym in [(x, s_) for x in STREAMS for s_ in ("SOLUSDT", "1000PEPEUSDT", "ARBUSDT", "DOGEUSDT")]:
    os.environ["TFH"] = str(tfh); E = importlib.reload(importlib.import_module(eng))
    B = bars("BTCUSDT", E); BT = [c["time"] for c in B]
    b = bars(sym, E); bT = [c["time"] for c in b]
    z = np.load(f"{dr}/{sym}.npz"); F2 = np.load(f"f2_{dr}/{sym}.npz")["F2"][:, [0, 1, 2, 5, 8]]
    F33 = np.full((len(z["t"]), 33), np.nan); F33[:, :28] = z["F"]; F33[:, 28:] = F2
    idx = np.flatnonzero((z["fam"] == fam) & (z["t"] >= 1704067200))
    for k in rng.choice(idx, 40, replace=False):
        i = int(z["i"][k])
        nb = 3000 if tfh == 4 else 4500   # as the bot fetches
        w = b[max(0, i - nb + 1):i + 1]
        bj = bisect.bisect_right(BT, bT[i])
        cs = V.dlm_candidates4(w, B[max(0, bj - nb):bj], streams=[ST], min_bars=0)
        m = [c for c in cs if c["side"] == int(z["side"][k])]
        tot += 1
        if not m: miss += 1; continue
        worst = np.maximum(worst, np.abs(np.array(m[0]["f"]) - F33[k].astype(np.float32).astype(float)))
    # no event the research did not have: bars with no wick1 event of a side -> the bot gives none either
    ev = {(int(i_), int(s_)) for i_, s_, f_ in zip(z["i"], z["side"], z["fam"]) if f_ == fam}
    for i in rng.choice(np.arange(3000, len(b)), 30, replace=False):
        nb = 3000 if tfh == 4 else 4500
        w = b[max(0, i - nb + 1):i + 1]; bj = bisect.bisect_right(BT, bT[i])
        for c in V.dlm_candidates4(w, B[max(0, bj - nb):bj], streams=[ST], min_bars=0):
            lv = c["lv"]; s = c["side"]
            filled = any(((b[j]["low"] <= lv) if s > 0 else (b[j]["high"] >= lv)) for j in range(i + 1, min(i + 5, len(b))))
            if filled and (int(i), s) not in ev: extra += 1
print("events", tot, "missed", miss, "extra", extra)
for j, nm in enumerate(V.DLM_FNAMES4): print(f"{nm:7s} {worst[j]:.6f}")
ok = miss == 0 and extra == 0 and worst.max() < 1e-3
print("OK" if ok else "FAIL"); sys.exit(0 if ok else 1)
