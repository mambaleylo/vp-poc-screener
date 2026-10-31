"""the ⚡ engine v2 (dlm_engine.py) against the bot's own dlm_candidates4: random coins and bars of both streams — the bot
given exactly what it sees live (its last 3000 4h / 4500 2h closed bars, BTC's the same) -> the same limits (side, level)
and the same 33 features (|diff| <= 1e-5 relative: the daily EMA50 of the 2h window — 375 days — has not fully decayed its start, ~5e-6)"""
import sys, os, json, random, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import V
import dlm_engine as E
m = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "vp_dlm_model.json")))
SD = {s["name"]: s for s in m["streams"]}
random.seed(7)
coins = ["SOLUSDT", "DOGEUSDT", "1000PEPEUSDT", "ARBUSDT", "WLDUSDT", "TIAUSDT", "AAVEUSDT", "ORDIUSDT"]
ok = True; nchk = 0; worst = 0.0
for stream in ("wick4h", "close2h"):
    p = E.STREAMS[stream]; B = E.btc_ctx(stream)
    T1, O1, H1, L1, C1, V1 = E.load1h("BTCUSDT"); bT, bO, bH, bL, bC, bV = E.chart(T1, O1, H1, L1, C1, V1, p["hh"])
    for bsym in coins:
        h1 = E.load1h(bsym); T, O, H, L, C, Vv = E.chart(*h1, p["hh"])
        ev = E.features(bsym, stream, B, h1)
        for _ in range(6):
            i = random.randrange(E.MIN_BARS + 100, len(C) - 1)
            w0 = max(0, i - p["nb"] + 1)
            bars = [{"time": int(T[k]), "open": O[k], "high": H[k], "low": L[k], "close": C[k], "volume": Vv[k]} for k in range(w0, i + 1)]
            j = np.searchsorted(bT, T[i], side="right"); bb = [{"time": int(bT[k]), "open": bO[k], "high": bH[k], "low": bL[k], "close": bC[k], "volume": bV[k]} for k in range(max(0, j - p["nb"]), j)]
            got = V.dlm_candidates4(bars, bb, streams=[SD[stream]], dmin=E.DMIN, dmax=E.DMAX, min_bars=E.MIN_BARS)
            mine = [k for k in range(len(ev["t"])) if ev["i"][k] == i] if ev else []
            if sorted(c["side"] for c in got) != sorted(int(ev["side"][k]) for k in mine):
                ok = False; print("  sides differ", stream, bsym, i, [c["side"] for c in got], [int(ev["side"][k]) for k in mine]); continue
            for c in got:
                k = next(k for k in mine if ev["side"][k] == c["side"])
                a, b = np.array(c["f"]), ev["f"][k]
                d = np.abs(a - b) / np.maximum(1.0, np.abs(a))
                worst = max(worst, float(d.max())); nchk += 1
                if d.max() > 1e-5 or abs(c["lv"] - ev["lv"][k]) > 1e-9 * abs(c["lv"]):
                    ok = False; print("  diff", stream, bsym, i, c["side"], {int(q): (round(float(a[q]), 6), round(float(b[q]), 6)) for q in np.flatnonzero(d > 1e-5)})
print(f"checked {nchk} limits, worst relative diff {worst:.2e}")
print("ALL OK" if ok and nchk > 40 else "FAILED"); sys.exit(0 if ok and nchk > 40 else 1)
