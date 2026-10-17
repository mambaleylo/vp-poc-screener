"""Peak Reversal v2: the bot's events / features / scores on live-sized history = the research's; trade record = label"""
import json, os, numpy as np
from common import V as vp, load, D
from nx_build import funding as fund_of
from prv_ev import STOPS, TAKES
CS, AGG, FU = {}, {}, {}
def h1_of(sym):
    if sym not in CS:
        CS[sym] = load(sym)
        AGG[sym] = {"4h": vp._oc_agg(CS[sym], 4), "1d": vp._oc_agg(CS[sym], 24)}
        FU[sym] = fund_of(sym)
    return CS[sym]
def closed(sym, tf, sec, n, now):
    sym = sym.replace("_", ""); h1_of(sym)
    bars = CS[sym] if tf == "1h" else AGG[sym][tf]
    return [c for c in bars if c["time"] + sec <= now][-n:]
vp._zm_closed = closed
vp._nx_funding = lambda sym, now: [x for x in FU[sym.replace("_", "")] if x[0] <= now][-100:]
MP = f"{D}/vp_prv_model.json"
m = json.load(open(MP)) if os.path.exists(MP) else None
rng = np.random.default_rng(5)
ok = bad = miss = 0; sdiff = 0.0; worst = np.zeros(13 + 89)
for sym in ("SOLUSDT", "LINKUSDT", "DOGEUSDT", "AVAXUSDT", "XRPUSDT", "ADAUSDT"):
    z = np.load(f"{D}/prv_ev/{sym}.npz")
    pick = np.where(z["t"] >= 1735689600)[0]
    for k in rng.choice(pick, 12, replace=False):
        t = int(z["t"][k]); x = z["X"][k].astype(float); tf = int(x[0])
        ref = {"btc": closed("BTCUSDT", "1h", 3600, 1000, t + 45), "eth": closed("ETHUSDT", "1h", 3600, 1000, t + 45)}
        evs = vp.prx_coin_events(sym.replace("USDT", "_USDT"), t + 45, ref, t)
        hit = [e for e in evs if e[0] == tf]
        if not hit:
            miss += 1; print("MISS", sym, tf, t, [e[0] for e in evs]); continue
        row = np.array(hit[0][2])
        d = np.abs(row - x) / (np.abs(x) + 1); worst = np.maximum(worst, d)
        if d.max() > 0.01:
            bad += 1
        else:
            ok += 1
        if m:
            s = int(x[1])
            a = sum(vp.zm_tree_pred(tt, list(row)) for tt in m["models"][str(s)]) / 3
            b = sum(vp.zm_tree_pred(tt, list(x)) for tt in m["models"][str(s)]) / 3
            sdiff = max(sdiff, abs(a - b))
print("events ok", ok, "off", bad, "miss", miss, "max score diff", round(sdiff, 4))
names = vp.PRX_BAND_NAMES + vp.NX_NAMES
for j in np.argsort(-worst)[:6]:
    print("  ", names[j], round(float(worst[j]), 5))
# ---- trade record = label (stop 1.5 ATR, take 3R, 48 bars)
vp.send_telegram = lambda *a, **k: None
vp.prx_save = lambda: None
vp.notify_trade_result = lambda *a, **k: None
vp.AUTOTRADE_ENABLED_PRV = False
def rng_c(sym, tf, a, b):
    s = sym.replace("_", ""); h1_of(s)
    bars = CS[s] if tf == "1h" else AGG[s][tf]
    return [c for c in bars if a <= c["time"] <= b]
vp.get_candles_range = rng_c
mm = {"rule": {"stop_atr": 1.5, "take_r": 3.0, "hold_bars": 48}}
si, ti = STOPS.index(1.5), TAKES.index(3.0)
ok2 = bad2 = 0
for sym in ("SOLUSDT", "LINKUSDT", "DOGEUSDT", "ETHUSDT"):
    z = np.load(f"{D}/prv_ev/{sym}.npz")
    pick = np.where((z["t"] >= 1735689600) & (z["t"] < 1788000000))[0]
    for k in rng.choice(pick, 15, replace=False):
        lab = float(z["Y"][k, si, ti])
        if lab != lab:
            continue
        t = int(z["t"][k]); x = z["X"][k]; tf = int(x[0]); s = int(x[1])
        cs = h1_of(sym) if tf == 1 else AGG[sym]["4h"]
        i = [c["time"] + tf * 3600 for c in cs].index(t)
        atr = vp.neuro_atr_series(cs, 14)[i]
        vp._PRX["trades"] = []
        vp.prx_open(mm, {"symbol": sym.replace("USDT", "_USDT"), "side": s, "tf": tf, "score": 0, "atr": atr, "px": 1.0}, t)
        vp.prx_settle(now=t + (48 + 2) * tf * 3600)
        tr = vp._PRX["trades"][0]
        if tr["r"] is not None and abs(tr["r"] - lab) < 0.01:
            ok2 += 1
        else:
            bad2 += 1; print("R DIFF", sym, tf, s, tr["result"], tr["r"], lab)
print("trades ok", ok2, "diff", bad2)
