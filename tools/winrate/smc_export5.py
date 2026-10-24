"""SMC v0.99.709: the hold 72 -> 96 h (smc_exits.py / port_smcx.py: 84..120 h all better, +0.79 -> +0.94R a trade). SMC v0.99.706: the model's threshold q 0.99 -> 0.993 and only the touches in the bot's reach at the hour's start (|px - lv| <= 1.5 dATR, its arm filter: 11-14% of the list were spikes to far levels the bot never arms; smc_reach2.py, port_smcr.py). Was (smc_q.py / smc_q2.py / port_smcq.py, port_smcq2.py: 558 -> 383 trades, +0.53 -> +0.76R, WR 61 -> 67%; the bundle with SMC at 1.5%: the median $12.6k -> $13.2k, the worst 10% $1.36k -> $1.87k, the last 12 months $19.2k -> $24.7k, the drawdown 57% -> 62%). Was: SMC v0.99.700: the honest pool (the bot's touch order) with the stop at a 4h close beyond 1 daily ATR and the emergency
stop at 2 dATR (smc_cstop.py: +0.42 -> +0.53R, WR 53 -> 61%; 1m +0.94 -> +1.07R): the backtest list (with "hs") and the
model's rule / research numbers"""
exec(open("smc_cstop.py").read().split('run("касанием 1 dATR (сейчас)"')[0])
QN = 0.993
thr = np.array([np.quantile(THR[Y], QN) if Y in THR else np.inf for Y in range(1970, 2030)])
idx = np.where((fam >= 33) & Dd["BOT"] & np.isfinite(SC) & (SC >= thr[np.clip(yr - 1970, 0, 59)]) & (T >= ts(2022)))[0]
OPEN = np.full(len(T), np.nan); by_ = {}
for i in idx: by_.setdefault(SYM[i], []).append(i)
for k_, lst in by_.items():
    Tb_, O_, H_, L_, C_, V_ = LE.load_np(Dd["names"][k_])
    for i in lst: OPEN[i] = O_[J[i]] if J[i] < len(O_) else np.nan
NEAR = SIDE * (OPEN - LV) / (LV * DATR / 100)
PX = np.full(len(T), np.nan)
for k_, lst in by_.items():
    Tb_, O_, H_, L_, C_, V_ = LE.load_np(Dd["names"][k_])
    for i in lst: PX[i] = C_[J[i] - 1] if J[i] >= 1 else np.nan
idx = idx[np.abs(PX[idx] - LV[idx]) / PX[idx] * 100 <= 1.5 * DATR[idx]]   # the bot's arm filter: in reach at the hour's start (smc_reach2.py)
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
        Rn[i], Kn[i], KD[i], EX[i] = wk2(O, H, L, C, Tb, int(J[i]), int(SIDE[i]), float(LV[i]), float(DATR[i]), HARD, 3.0, 96, KH)
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
json.dump(out, open("smc_bt_v709.json", "w"), separators=(",", ":"))
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
M = json.load(open("/home/user/vp-poc-screener/vp_smc_model.json"))
M.update({"ver": 4, "q": QN, "thr": round(float(np.quantile(THR[2026], QN)), 6), "thr_from": "2025 out of sample (the walk-forward rule), q 0.993"})
M["rule"].update({"stop_close_h": KH, "hard_x": HARD, "hold_h": 96})
M["research"].update({"years": years, "max_losing_streak": mx, "avg": round(float(rr.mean()), 3), "wr": round(float((rr > 0).mean() * 100), 1),
                      "per_month": round(len(rr) / ((ts(2026, 10) - ts(2022)) / (30.4 * 86400)), 1)})
json.dump(M, open("vp_smc_model_v709.json", "w"), separators=(",", ":"))
print("list", len(out), "avg", M["research"]["avg"], "wr", M["research"]["wr"], "streak", mx, {k_: sum(1 for x in out if x["k"] == k_) for k_ in KN.values()})
