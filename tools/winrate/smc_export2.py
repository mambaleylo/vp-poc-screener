"""SMC (v0.99.699): the honest backtest list — the touches of an hour in the order the bot gets them (the nearer level to
the hour's open first; the list had them by the model's score — a look-ahead: +0.67R -> +0.42R, smc_order.py); the
deployed model unchanged, its research numbers re-written"""
import json, os, numpy as np
import lv_engine as LE
from lv_wf import ts
from bt_trades import gate_sym
src = open("smc_order.py").read().split("def show(")[0]
exec(src)
sel = select(NEAR)
HONEST = [dict(s=Dd["names"][Dd["SYM"][i]], t=int(Dd["T"][i]), x=int(Dd["T"][i] + Dd["K"][e][i] * 3600), d=int(Dd["SIDE"][i]),
               fam=LE.FAMS[fam[i]], r=float(Dd["R"][e][i])) for i in sel]
print("honest trades", len(HONEST), round(float(np.mean([w["r"] for w in HONEST])), 3))

W = HONEST
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
json.dump(out, open("smc_bt_v699.json", "w"), separators=(",", ":"))
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
M = json.load(open("/home/user/vp-poc-screener/vp_smc_model.json"))
M["research"].update({"years": years, "max_losing_streak": mx, "avg": round(float(rr.mean()), 3), "wr": round(float((rr > 0).mean() * 100), 1),
                      "per_month": round(len(rr) / ((ts(2026, 10) - ts(2022)) / (30.4 * 86400)), 1), "order": "near"})
json.dump(M, open("vp_smc_model_v699.json", "w"), separators=(",", ":"))
print("avg", M["research"]["avg"], "wr", M["research"]["wr"], "streak", mx)
