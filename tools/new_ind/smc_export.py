"""SMC v1 export (v0.99.678): the 2026 walk-forward model (LightGBM x2 seeds, the walk-forward params) on all the bot coins' SMC
touches (lv2 fam >= 33: unfilled FVG on 4h / 1d / 1w, untouched swings on 1d / 1w, order blocks on 4h / 1d; both
sides), label E2 (stop 1 daily ATR, take 3R, 72 h), trained on everything closed before 2026; thr = q 0.99 of its
scores on 2026 (out of sample: the final model's in-sample scores were inflated, its threshold would let ~5x fewer trades); the backtest
list = the walk-forward trades (q 0.99, cap 12, bot coins, 2022+) re-simulated for the exit kind / price."""
import json, glob, os, numpy as np, lightgbm as lgb
from lv_wf import load_dir, ts
import lv_engine as LE
from lgbpure import export
from bt_trades import gate_sym
Dd = load_dir("lv2", LE.FNAMES)
F = Dd["F"]; fam = F[:, 0].astype(int); T = Dd["T"]
y = np.nan_to_num(Dd["R"][2], nan=0.0).clip(-1.2, 6.0)
now = int(T.max())
CUT = ts(2026) - 14 * 86400   # the 2026 walk-forward model: trained before 2026, its threshold from its own 2026 scores
tr = (fam >= 33) & Dd["BOT"] & (T < CUT)
pr = dict(n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=300, subsample=0.7, subsample_freq=1,
          colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
models, sc = [], np.zeros(len(T))
for s_ in range(2):
    m = lgb.LGBMRegressor(random_state=s_, **pr).fit(F[tr], y[tr])
    models.append(export(m.booster_, LE.FNAMES)["trees"])
    sc += m.predict(F) / 2
last = (fam >= 33) & Dd["BOT"] & (T >= ts(2026))
# the walk-forward rule of the backtest list: the threshold of 2026 = q 0.99 of the 2025 out-of-sample scores (the 2025
# model's); the deployed model IS the 2026 walk-forward model (the same data cut, params and seeds), so the bot makes
# the 2026 trades of the list. (Its in-sample quantile was inflated: ~5x fewer trades.)
_z = np.load("smc_sc.npz", allow_pickle=True)
thr = float(np.quantile(_z["THR"].item()[2026], 0.99))
print("own 2026 OOS q0.99 would be", round(float(np.quantile(sc[last], 0.99)), 4))
print("trained on", int(tr.sum()), "thr q0.99", round(thr, 6), "last-year events", int(last.sum()))
# ---- the backtest list: the walk-forward trades ----
W = json.load(open("smc_trades.json"))["0.99_bot"]
STOP, TAKE, HOLD = 1.0, 3.0, 72
def sim(O, H, L, C, j, side, fill, datr):
    n = len(C); risk = fill * STOP * datr / 100; stop = fill - side * risk; tp = fill + side * TAKE * risk
    e = min(n, j + HOLD); k = e - 1 - j; ex = C[e - 1]; kind = "time"
    for q in range(e - j):
        b = j + q
        if (side > 0 and L[b] <= stop) or (side < 0 and H[b] >= stop):
            gap = (side > 0 and O[b] <= stop) or (side < 0 and O[b] >= stop)
            ex = O[b] if (gap and q > 0) else stop; k = q; kind = "stop"; break
        if q > 0 and ((side > 0 and H[b] >= tp) or (side < 0 and L[b] <= tp)):
            ex = tp; k = q; kind = "take"; break
    fee = (0.001 + 0.0003 * (k + 1) / 24) * fill / risk
    return side * (ex - fill) / risk - fee, k + 1, kind, ex
out, bad = [], 0
bysym = {}
for w in W: bysym.setdefault(w["s"], []).append(w)
TFN = {"fvg4": "4h", "fvgd": "1d", "fvgw": "1w", "swd": "1d", "sww": "1w", "obd": "1d", "ob4": "4h"}
for sym, lst in bysym.items():
    z = np.load(f"lv2/{sym}.npz")
    Tb, O, H, L, C, V = LE.load_np(sym)
    for w in lst:
        fi = LE.FAMS.index(w["fam"])
        k = np.flatnonzero((z["t"] == w["t"]) & (z["fam"] == fi) & (z["side"] == w["d"]))
        if len(k) != 1: bad += 1; continue
        k = int(k[0]); j = int(z["j"][k]); lv = float(z["lv"][k]); datr = float(z["datr"][k])
        r, kk, kind, ex = sim(O, H, L, C, j, w["d"], lv, datr)
        if abs(r - w["r"]) > 1e-3: bad += 1
        gs, scl = gate_sym(sym); risk = lv * STOP * datr / 100
        out.append({"s": gs, "d": w["d"], "c": "1h", "tf": TFN[w["fam"].split("_")[0]], "lvl": w["fam"], "t": w["t"],
                    "e": round(lv / scl, 10), "sl": round((lv - w["d"] * risk) / scl, 10), "tp": round((lv + w["d"] * TAKE * risk) / scl, 10),
                    "x": int(w["t"] + kk * 3600), "xp": round(float(ex) / scl, 10), "r": round(float(r), 3), "k": kind})
print("backtest list", len(out), "mismatch", bad)
out.sort(key=lambda x: x["t"])
json.dump(out, open("smc_bt_v678.json", "w"), separators=(",", ":"))
rr = np.array([x["r"] for x in out]); tt = np.array([x["t"] for x in out])
years = {}
for Y in range(2022, 2027):
    msk = (tt >= ts(Y)) & (tt < ts(Y + 1)); rs = rr[msk]
    if not msk.any(): continue
    o = np.argsort(tt[msk]); c = np.cumsum(rs[o]); dd = float(np.max(np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c]))
    wk = ((ts(Y + 1) if Y < 2026 else ts(2026, 10)) - ts(Y)) / 604800
    years[str(Y)] = {"n": int(msk.sum()), "avg": round(float(rs.mean()), 3), "wk": round(float(msk.sum() / wk), 1),
                     "sum": round(float(rs.sum()), 1), "dd": round(dd, 1), "wr": round(float((rs > 0).mean() * 100), 1)}
    print(Y, years[str(Y)])
run = mx = 0
for x in sorted(out, key=lambda x: x["x"]):
    run = run + 1 if x["r"] < 0 else 0; mx = max(mx, run)
model = {"ver": 1, "kind": "smc", "feats": LE.FNAMES, "fams": LE.FAMS, "smc_fams": LE.FAMS[33:], "models": models, "thr": round(thr, 6),
         "q": 0.99, "side_cap": 12, "trained_to": CUT, "thr_from": "2025 out of sample (the walk-forward rule)",
         "rule": {"stop_datr": STOP, "take_r": TAKE, "hold_h": HOLD},
         "research": {"coins": 127, "check_coins": 84, "q": 0.99, "cap": 12, "years": years, "max_losing_streak": mx,
                      "avg": round(float(rr.mean()), 3), "wr": round(float((rr > 0).mean() * 100), 1),
                      "per_month": round(len(rr) / ((ts(2026, 10) - ts(2022)) / (30.4 * 86400)), 1),
                      "check": {"avg": 0.58, "wr": 57.0, "x_year": 3.06}, "x_year": 3.2}}
json.dump(model, open("vp_smc_model_v1.json", "w"), separators=(",", ":"))
print("model size", os.path.getsize("vp_smc_model_v1.json"), "avg", model["research"]["avg"], "wr", model["research"]["wr"], "streak", mx)
