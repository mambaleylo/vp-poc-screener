"""📏 HTF v0.99.773 (the user: "для htf ещё тоже полную проверку, новые гипотезы…", the answer "досягаемость 2,5"): the bot arms
a level up to 2.5 daily ATR from the price at the hour's start (rule.reach_datr 1.5 -> 2.5: htf_var.py + money_ema.py MOD=htf,
the bundle with HTF — the usual year +10% in 6 of 6 paired noise runs, the last 12 months +4% in 5 of 6, the drawdown the
same). The backtest list re-made on the clean 2020- candles (fill_gaps.py) by the deployed recipe's yearly walk-forward
models, 2026 by the bot's own two models and thresholds (d26). The models, thresholds and the other rules unchanged.
-> vp_bt_trades.json "htf", vp_htf_model.json (rule.reach_datr 2.5, the research numbers). Run in the lab dir (smclab/README.md)."""
import os, sys, json, numpy as np
sys.argv = ["x"]
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..", "..")
import htf_var as HV
from lv_wf import ts
import lv_engine as LE
def gate_sym(sym):   # = tools/adaptation/bt_trades.py
    b = sym[:-4]
    return (b[4:] if b.startswith("1000") else b) + "_USDT", (1000.0 if b.startswith("1000") else 1.0)
p = dict(HV.BASE); p.update(HV.VARS["d26"]); p.update(HV.VARS["reach25"])
L = HV.build(p, detail=True)
TFN = lambda f: "1d" if LE.SCOPE[LE.FAMS.index(f)] == 0 else ("1w" if LE.SCOPE[LE.FAMS.index(f)] == 1 else "1M")
out = []
for x in L:
    gs, scl = gate_sym(x["sym"]); f = x["e"]; rk = x["risk"]
    out.append({"s": gs, "d": 1, "c": "1h", "tf": TFN(x["lvl"]), "lvl": x["lvl"], "t": x["t0"], "e": round(f / scl, 10),
                "sl": round((f - rk) / scl, 10), "hs": round((f - p["hard"] * rk) / scl, 10), "tp": round((f + p["take"] * rk) / scl, 10),
                "x": x["t1"], "xp": round(x["ex"] / scl, 10), "r": round(x["r"], 3), "k": x["kind"], "by": x["by"]})
out.sort(key=lambda y: y["t"])
rr = np.array([y["r"] for y in out]); tt = np.array([y["t"] for y in out]); years = {}
for Y in range(2023, 2027):
    m = (tt >= ts(Y)) & (tt < ts(Y + 1))
    if not m.any(): continue
    o = np.argsort(np.array([y["x"] for y in out])[m]); c = np.cumsum(rr[m][o]); dd = float(np.max(np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c]))
    wk = ((ts(Y + 1) if Y < 2026 else ts(2026, 10)) - ts(Y)) / 604800
    years[str(Y)] = {"n": int(m.sum()), "avg": round(float(rr[m].mean()), 3), "wk": round(float(m.sum() / wk), 1), "sum": round(float(rr[m].sum()), 1),
                     "dd": round(dd, 1), "wr": round(float((rr[m] > 0).mean() * 100), 1)}
    print(Y, years[str(Y)], flush=True)
run_ = mx = 0
for y in sorted(out, key=lambda y: y["x"]):
    run_ = run_ + 1 if y["r"] < 0 else 0; mx = max(mx, run_)
bt = json.load(open(f"{ROOT}/vp_bt_trades.json")); bt["htf"] = out
json.dump(bt, open(f"{ROOT}/vp_bt_trades.json", "w"), separators=(",", ":"))
M = json.load(open(f"{ROOT}/vp_htf_model.json"))
M["rule"]["reach_datr"] = 2.5
M["research"].update({"years": years, "max_losing_streak": mx, "avg": round(float(rr.mean()), 3), "wr": round(float((rr > 0).mean() * 100), 1),
                      "per_month": round(len(rr) / ((ts(2026, 10) - ts(2023)) / (30.4 * 86400)), 1)})
json.dump(M, open(f"{ROOT}/vp_htf_model.json", "w"), separators=(",", ":"))
from collections import Counter
print("list", len(out), "avg", round(float(rr.mean()), 3), "wr", round(float((rr > 0).mean() * 100), 1), "streak", mx, Counter(y["k"] for y in out))
