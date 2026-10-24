"""SMC v0.99.700: the honest pool (the bot's touch order) with the stop at a 4h close beyond 1 daily ATR and the emergency
stop at 2 dATR (smc_cstop.py: +0.42 -> +0.53R, WR 53 -> 61%; 1m +0.94 -> +1.07R): the backtest list (with "hs") and the
model's rule / research numbers"""
exec(open("smc_cstop.py").read().split('run("касанием 1 dATR (сейчас)"')[0])
from bt_trades import gate_sym
@njit
def wk2(O, H, L, C, Tb, j, s, fill, datr, hard_a, take, hold, kh):
    risk = fill * datr / 100; ssl = fill - s * risk; hsl = fill - s * hard_a * risk; tp = fill + s * take * risk
    n = len(C); e = min(n, j + hold)
    for q in range(e - j):
        b = j + q
        if (s > 0 and L[b] <= hsl) or (s < 0 and H[b] >= hsl):
            x = O[b] if (q > 0 and ((s > 0 and O[b] <= hsl) or (s < 0 and O[b] >= hsl))) else hsl
            return s * (x - fill) / risk - (0.001 + 0.0003 * (q + 1) / 24) * fill / risk, q + 1, 0, x
        if q > 0 and ((s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp)):
            return s * (tp - fill) / risk - (0.001 + 0.0003 * (q + 1) / 24) * fill / risk, q + 1, 1, tp
        if (Tb[b] + 3600) % (kh * 3600) == 0 and ((s > 0 and C[b] <= ssl) or (s < 0 and C[b] >= ssl)):
            return s * (C[b] - fill) / risk - (0.001 + 0.0003 * (q + 1) / 24) * fill / risk, q + 1, 4, C[b]
    b = e - 1
    return s * (C[b] - fill) / risk - (0.001 + 0.0003 * (e - j) / 24) * fill / risk, e - j, 3, C[b]
HARD, KH = 2.0, 4
Rn = np.full(len(T), np.nan); Kn = np.zeros(len(T), np.int64); KD = np.zeros(len(T), np.int64); EX = np.zeros(len(T))
for k in sorted(set(SYM[idx])):
    Tb, O, H, L, C = bars_of(k)
    for i in idx[SYM[idx] == k]:
        Rn[i], Kn[i], KD[i], EX[i] = wk2(O, H, L, C, Tb, int(J[i]), int(SIDE[i]), float(LV[i]), float(DATR[i]), HARD, 3.0, 72, KH)
R, K = Rn, Kn
sel = select(NEAR)
TFN = {"fvg4": "4h", "fvgd": "1d", "fvgw": "1w", "swd": "1d", "sww": "1w", "obd": "1d", "ob4": "4h"}
KN = {0: "hard", 1: "take", 3: "time", 4: "stop"}
out = []
for i in sel:
    gs, scl = gate_sym(Dd["names"][SYM[i]]); s = int(SIDE[i]); lv = float(LV[i]); risk = lv * float(DATR[i]) / 100; fm = LE.FAMS[fam[i]]
    out.append({"s": gs, "d": s, "c": "1h", "tf": TFN[fm.split("_")[0]], "lvl": fm, "t": int(T[i]), "e": round(lv / scl, 10),
                "sl": round((lv - s * risk) / scl, 10), "hs": round((lv - s * HARD * risk) / scl, 10), "tp": round((lv + s * 3.0 * risk) / scl, 10),
                "x": int(T[i] + K[i] * 3600), "xp": round(float(EX[i]) / scl, 10), "r": round(float(R[i]), 3), "k": KN[int(KD[i])]})
out.sort(key=lambda x: x["t"])
json.dump(out, open("smc_bt_v700.json", "w"), separators=(",", ":"))
rr = np.array([x["r"] for x in out]); tt = np.array([x["t"] for x in out])
years = {}
for Y in range(2022, 2027):
    msk = (tt >= ts(Y)) & (tt < ts(Y + 1)); rs = rr[msk]
    if not msk.any(): continue
    o = np.argsort(tt[msk]); c = np.cumsum(rs[o]); dd = float(np.max(np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c]))
    wk_ = ((ts(Y + 1) if Y < 2026 else ts(2026, 10)) - ts(Y)) / 604800
    years[str(Y)] = {"n": int(msk.sum()), "avg": round(float(rs.mean()), 3), "wk": round(float(msk.sum() / wk_), 1),
                     "sum": round(float(rs.sum()), 1), "dd": round(dd, 1), "wr": round(float((rs > 0).mean() * 100), 1)}
    print(Y, years[str(Y)])
run_ = mx = 0
for x in sorted(out, key=lambda x: x["x"]):
    run_ = run_ + 1 if x["r"] < 0 else 0; mx = max(mx, run_)
M = json.load(open("vp_smc_model_v699.json"))
M["rule"].update({"stop_close_h": KH, "hard_x": HARD})
M["research"].update({"years": years, "max_losing_streak": mx, "avg": round(float(rr.mean()), 3), "wr": round(float((rr > 0).mean() * 100), 1),
                      "per_month": round(len(rr) / ((ts(2026, 10) - ts(2022)) / (30.4 * 86400)), 1)})
json.dump(M, open("vp_smc_model_v700.json", "w"), separators=(",", ":"))
print("list", len(out), "avg", M["research"]["avg"], "wr", M["research"]["wr"], "streak", mx, {k_: sum(1 for x in out if x["k"] == k_) for k_ in KN.values()})
