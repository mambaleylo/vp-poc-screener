"""SMC v0.99.771 (the user: "полную проверку и попытку улучшить по smc", the answer "да, тейк 4R"): the deployed rule with the take
4R instead of 3R (smc_var.py + money_ema.py MOD=smc: the bundle's last 12 months +35% in 6 of 6 paired noise runs, the usual
year and the drawdown the same) and the backtest list as the bot trades it: the events at ANY touch of a level (lv_engine
LV_TOUCH=0; the lab had wanted 0.1% past it), 2026 by the bot's own model and thr (the other years by the yearly walk-forward
models of the deployed recipe), on the clean 2020- candles (fill_gaps.py). The model's trees and thr unchanged (ver 4).
-> vp_bt_trades.json "smc", vp_smc_model.json (rule.take_r 4, the research numbers). Run in the SMC lab dir (smclab/README.md)."""
import os, sys, json, numpy as np
sys.argv = ["x"]
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..", "..")
import smc_var as SV
from lv_wf import ts
def gate_sym(sym):   # = tools/adaptation/bt_trades.py
    b = sym[:-4]
    return (b[4:] if b.startswith("1000") else b) + "_USDT", (1000.0 if b.startswith("1000") else 1.0)
p = dict(SV.BASE); p.update(SV.VARS["t0"]); p.update(SV.VARS["take4"]); p.update(SV.VARS["d26"])
L = SV.build(p, detail=True)
TFN = {"fvg4": "4h", "fvgd": "1d", "fvgw": "1w", "swd": "1d", "sww": "1w", "obd": "1d", "ob4": "4h"}
out = []
for x in L:
    gs, scl = gate_sym(x["sym"]); s = x["side"]; f = x["e"]; rk = x["risk"]
    y = {"s": gs, "d": s, "c": "1h", "tf": TFN[x["lvl"].split("_")[0]], "lvl": x["lvl"], "t": x["t0"], "e": round(f / scl, 10),
         "sl": round((f - s * rk) / scl, 10), "hs": round((f - s * p["hard"] * rk) / scl, 10), "tp": round((f + s * p["take"] * rk) / scl, 10),
         "x": x["t1"], "xp": round(x["ex"] / scl, 10), "r": round(x["r"], 3), "k": x["kind"]}
    if x["kind"] == "be2": y["be"] = x["be_t"]
    out.append(y)
out.sort(key=lambda y: y["t"])
rr = np.array([y["r"] for y in out]); tt = np.array([y["t"] for y in out]); years = {}
for Y in range(2022, 2027):
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
bt = json.load(open(f"{ROOT}/vp_bt_trades.json")); bt["smc"] = out
json.dump(bt, open(f"{ROOT}/vp_bt_trades.json", "w"), separators=(",", ":"))
M = json.load(open(f"{ROOT}/vp_smc_model.json"))
M["rule"]["take_r"] = 4.0
M["research"].update({"years": years, "max_losing_streak": mx, "avg": round(float(rr.mean()), 3), "wr": round(float((rr > 0).mean() * 100), 1),
                      "per_month": round(len(rr) / ((ts(2026, 10) - ts(2022)) / (30.4 * 86400)), 1), "q": M.get("q", 0.993)})
json.dump(M, open(f"{ROOT}/vp_smc_model.json", "w"), separators=(",", ":"))
from collections import Counter
print("list", len(out), "avg", round(float(rr.mean()), 3), "wr", round(float((rr > 0).mean() * 100), 1), "streak", mx, Counter(y["k"] for y in out))
