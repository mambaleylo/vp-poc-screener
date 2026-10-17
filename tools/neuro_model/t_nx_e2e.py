import json, os, sys, numpy as np
from common import V as vp, load, D
from nx_build import funding as fund_of, STOPS, TAKES, HOLDS
import nx_feat
assert vp.NX_NAMES == nx_feat.NAMES, "names differ"
CS, AGG, FU = {}, {}, {}
def h1_of(sym):
    if sym not in CS:
        CS[sym] = load(sym)
        AGG[sym] = {"4h": vp._oc_agg(CS[sym], 4), "1d": vp._oc_agg(CS[sym], 24)}
        FU[sym] = fund_of(sym)
    return CS[sym]
def closed(sym, tf, sec, n, now):
    sym = sym.replace("_", "")
    h1_of(sym)
    bars = CS[sym] if tf == "1h" else AGG[sym][tf]
    return [c for c in bars if c["time"] + sec <= now][-n:]
vp._zm_closed = closed
vp._nx_funding = lambda sym, now: [x for x in FU[sym.replace("_", "")] if x[0] <= now][-100:]
MP = f"{D}/vp_neuro_model.json"
m = json.load(open(MP)) if os.path.exists(MP) else None
rng = np.random.default_rng(7)
worst = np.zeros(len(vp.NX_NAMES)); n_ok = n_bad = 0; sdiff = 0.0
for sym in ("SOLUSDT", "LINKUSDT", "DOGEUSDT", "AVAXUSDT", "XRPUSDT", "ADAUSDT"):
    z = np.load(f"{D}/nx/{sym}.npz")
    pick = np.where(z["t"] >= 1735689600)[0]
    for k in rng.choice(pick, 10, replace=False):
        t = int(z["t"][k]); now = t + 3600 + 45
        ref = {"btc": closed("BTCUSDT", "1h", 3600, 1000, now), "eth": closed("ETHUSDT", "1h", 3600, 1000, now)}
        row, h1 = vp.nx_coin_row(sym.replace("USDT", "_USDT"), now, ref)
        x = z["X"][k].astype(float)
        dif = np.abs(np.array(row) - x) / (np.abs(x) + 1)
        worst = np.maximum(worst, dif)
        if dif.max() > 0.01:
            n_bad += 1
        else:
            n_ok += 1
        if m:
            a, b = vp.nx_score(m, row), vp.nx_score(m, list(x))
            sdiff = max(sdiff, abs(a[1] - b[1]), abs(a[-1] - b[-1]))
print("rows ok", n_ok, "off", n_bad, "max score diff", round(sdiff, 4))
for j in np.argsort(-worst)[:8]:
    print("  ", vp.NX_NAMES[j], round(float(worst[j]), 5))
if not m:
    sys.exit()
# ---- the trade record: nx_open + nx_settle on 1h candles = the research label
vp.send_telegram = lambda *a, **k: None
vp.nx_save = lambda: None
vp.notify_trade_result = lambda *a, **k: None
vp.AUTOTRADE_ENABLED_NEURO = False
vp.get_candles_range = lambda sym, tf, a, b: [c for c in h1_of(sym.replace("_", "")) if a <= c["time"] <= b]
vp._NX["model"] = m
R = m["rule"]
ai, ti, hi = STOPS.index(R["stop_atr"]), TAKES.index(R["take_r"]), HOLDS.index(R["hold_h"])
ok2 = bad2 = 0
for sym in ("SOLUSDT", "LINKUSDT", "DOGEUSDT", "AVAXUSDT", "ETHUSDT"):
    z = np.load(f"{D}/nx/{sym}.npz")
    pick = np.where(z["t"] >= 1735689600)[0]
    for k in rng.choice(pick, 12, replace=False):
        t = int(z["t"][k]); h = t + 3600
        for si, s in enumerate((1, -1)):
            lab = float(z["Y"][k, si, ai, ti, hi])
            if lab != lab:
                continue
            atr = z["X"][k][vp.NX_NAMES.index("atr_pct")] / 100 * h1_of(sym)[int(z["i"][k])]["close"]
            vp._NX["trades"] = []
            vp.nx_open(m, {"symbol": sym.replace("USDT", "_USDT"), "side": s, "score": 0, "atr": float(atr), "px": 1.0}, h)
            vp.nx_settle(now=h + (R["hold_h"] + 6) * 3600)
            tr = vp._NX["trades"][0]
            if tr["r"] is not None and abs(tr["r"] - lab) < 0.01:
                ok2 += 1
            else:
                bad2 += 1
                print("R DIFF", sym, s, tr["result"], tr["r"], lab)
print("trades ok", ok2, "diff", bad2)
