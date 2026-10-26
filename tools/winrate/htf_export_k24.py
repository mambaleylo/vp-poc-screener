"""📏 HTF v2 (v0.99.738): the stop on the 1d close (was 4h) — the list re-walked, the models unchanged.\nWas: 📏 HTF v1 export (v0.99.732): the two 2026 walk-forward models (LightGBM x2 seeds, the walk-forward params, trained on
everything of the bot coins closed 14 days before 2026), exactly the models that made the 2026 trades of the backtest:
  "o" = the HTF levels (lv2 fam 0..22, both sides), label E2 (stop 1 dATR, take 3R, 72 h) — div_screen.py's model
  "n" = the long HTF touches only, label = the traded exit (the soft stop 1 dATR at a 4h close, the hard 3 dATR, take 3R, 96 h)
A long touch is taken when either model's score is above its threshold = q 0.995 of its 2025 out-of-sample scores (the
walk-forward rule of 2026; a score > thr <=> its percentile >= 0.995). The scores re-made here are checked against the
walk-forward ones. The backtest list = the deployed rule's trades 2023-26 (htf_sym.py's selection) with the exit kind."""
import sys, json, glob, math, numpy as np, lightgbm as lgb, warnings; warnings.filterwarnings("ignore")
sys.argv = ["x"]
from numba import njit
from lv_wf import load_dir, ts
import lv_engine as LE
from lgbpure import export
from bt_trades import gate_sym
Dd = load_dir("lv2", LE.FNAMES); F = Dd["F"]; fam = F[:, 0].astype(int); T, SIDE, SYM, BOT = Dd["T"], Dd["SIDE"], Dd["SYM"], Dd["BOT"]
LV, J, DT = [], [], []
for fn in sorted(glob.glob("lv2/*.npz")):
    z = np.load(fn)
    if len(z["t"]) == 0: continue
    LV.append(z["lv"]); J.append(z["j"]); DT.append(z["datr"])
LV, J, DATR = np.concatenate(LV), np.concatenate(J).astype(np.int64), np.concatenate(DT)
zo = np.load("div_lv2_1537_sc.npz", allow_pickle=True); SCo, THRo = zo["SC"], zo["THR"].item()
zn = np.load("htf_long_sc.npz", allow_pickle=True); SCn, THRn, RL = zn["SC"], zn["THR"].item(), zn["RL"]
CUT = ts(2026) - 14 * 86400
pr = dict(n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=300, subsample=0.7, subsample_freq=1,
          colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
HTF = fam <= 22
LONG = HTF & (SIDE > 0) & (T >= ts(2019)) & np.isfinite(DATR)
# ---- the backtest list: the deployed rule (htf_sym.py) with the exit kind / price ----
def pct(SCx, THRx):
    yr = np.array([int(np.datetime64(int(t), "s").astype("datetime64[Y]").astype(int) + 1970) for t in T]); p = np.full(len(T), np.nan)
    for Y, v in THRx.items():
        m = (yr == Y) & np.isfinite(SCx)
        if m.any(): p[m] = np.searchsorted(np.sort(v), SCx[m]) / len(v)
    return p, yr
Po, yr = pct(SCo, THRo); Pn, _ = pct(SCn, THRn)
rule = HTF & (SIDE > 0) & (T >= ts(2023)) & BOT & np.isfinite(Po) & np.isfinite(Pn) & ((Po >= 0.995) | (Pn >= 0.995))
cand = np.where(rule)[0]
@njit
def wk2(O, H, L, C, Tb, j, fill, datr, hard_a, take, hold, kh):
    risk = fill * datr / 100; ssl = fill - risk; hsl = fill - hard_a * risk; tp = fill + take * risk
    n = len(C); e = min(n, j + hold)
    for q in range(e - j):
        b = j + q
        if L[b] <= hsl:
            x = O[b] if (q > 0 and O[b] <= hsl) else hsl
            return (x - fill) / risk - (0.001 + 0.0003 * (q + 1) / 24) * fill / risk, q + 1, 0, x
        if q > 0 and H[b] >= tp:
            return (tp - fill) / risk - (0.001 + 0.0003 * (q + 1) / 24) * fill / risk, q + 1, 1, tp
        if (Tb[b] + 3600) % (kh * 3600) == 0 and C[b] <= ssl:
            return (C[b] - fill) / risk - (0.001 + 0.0003 * (q + 1) / 24) * fill / risk, q + 1, 4, C[b]
    b = e - 1
    return (C[b] - fill) / risk - (0.001 + 0.0003 * (e - j) / 24) * fill / risk, e - j, 3, C[b]
R = np.full(len(T), np.nan); K = np.zeros(len(T), np.int64); KD = np.zeros(len(T), np.int64); EX = np.zeros(len(T)); OPEN = np.full(len(T), np.nan); PX = np.full(len(T), np.nan)
for k in sorted(set(SYM[cand])):
    Tb, O, H, L, C, V = LE.load_np(Dd["names"][k])
    for i in cand[SYM[cand] == k]:
        OPEN[i] = O[J[i]]; PX[i] = C[J[i] - 1]
        R[i], K[i], KD[i], EX[i] = wk2(O, H, L, C, Tb, int(J[i]), float(LV[i]), float(DATR[i]), 3.0, 3.0, 96, 24)
cand = cand[np.abs(PX[cand] - LV[cand]) / PX[cand] * 100 <= 1.5 * DATR[cand]]
NEAR = (OPEN - LV) / (LV * DATR / 100)
o = cand[np.lexsort((NEAR[cand], T[cand]))]
busy, act, sel = {}, [], []
for i in o:
    t = T[i]
    if busy.get(SYM[i], 0) > t: continue
    act = [a for a in act if a > t]
    if len(act) >= 12: continue
    end = t + int(K[i]) * 3600; busy[SYM[i]] = end; act.append(end); sel.append(i)
KN = {0: "hard", 1: "take", 3: "time", 4: "stop"}
TFN = lambda f: "1d" if LE.SCOPE[LE.FAMS.index(f)] == 0 else ("1w" if LE.SCOPE[LE.FAMS.index(f)] == 1 else "1M")
out = []
for i in sel:
    gs, scl = gate_sym(Dd["names"][SYM[i]]); lv = float(LV[i]); risk = lv * float(DATR[i]) / 100; fm = LE.FAMS[fam[i]]
    out.append({"s": gs, "d": 1, "c": "1h", "tf": TFN(fm), "lvl": fm, "t": int(T[i]), "e": round(lv / scl, 10), "sl": round((lv - risk) / scl, 10),
                "hs": round((lv - 3 * risk) / scl, 10), "tp": round((lv + 3 * risk) / scl, 10), "x": int(T[i] + K[i] * 3600),
                "xp": round(float(EX[i]) / scl, 10), "r": round(float(R[i]), 3), "k": KN[int(KD[i])],
                "by": ("o" if Po[i] >= 0.995 else "") + ("n" if Pn[i] >= 0.995 else "")})
out.sort(key=lambda x: x["t"])
rr = np.array([x["r"] for x in out]); tt = np.array([x["t"] for x in out])
years = {}
for Y in range(2023, 2027):
    msk = (tt >= ts(Y)) & (tt < ts(Y + 1)); rs = rr[msk]
    if not msk.any(): continue
    oo = np.argsort(tt[msk]); c = np.cumsum(rs[oo]); dd = float(np.max(np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c]))
    wk = ((ts(Y + 1) if Y < 2026 else ts(2026, 10)) - ts(Y)) / 604800
    years[str(Y)] = {"n": int(msk.sum()), "avg": round(float(rs.mean()), 3), "wk": round(float(msk.sum() / wk), 1), "sum": round(float(rs.sum()), 1),
                     "dd": round(dd, 1), "wr": round(float((rs > 0).mean() * 100), 1)}
    print(Y, years[str(Y)], flush=True)
run_ = mx = 0
for x in sorted(out, key=lambda x: x["x"]):
    run_ = run_ + 1 if x["r"] < 0 else 0; mx = max(mx, run_)
print("list", len(out), "avg", round(float(rr.mean()), 3), "by o/n/both", sum(x["by"] == "o" for x in out), sum(x["by"] == "n" for x in out), sum(x["by"] == "on" for x in out), flush=True)
M = json.load(open("/home/user/vp-poc-screener/vp_htf_model.json"))
M["rule"]["stop_close_h"] = 24
M["trained_to"] = int(M["trained_to"]) + 1   # the same models; a later stamp so the running bots take the new rule
M["research"] = {"years": years, "max_losing_streak": mx, "avg": round(float(rr.mean()), 3), "wr": round(float((rr > 0).mean() * 100), 1),
                 "per_month": round(len(rr) / ((ts(2026, 10) - ts(2023)) / (30.4 * 86400)), 1)}
json.dump(M, open("vp_htf_model_k24.json", "w"), separators=(",", ":"))
json.dump(out, open("htf_bt_v2_k24.json", "w"), separators=(",", ":"))
print("model rule", M["rule"], "trained_to", M["trained_to"])
