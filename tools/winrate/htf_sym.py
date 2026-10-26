"""HTF levels (lv2 fam <= 22) on the realistic pipeline (the bot's reach filter |px - lv| <= 1.5 dATR at the hour's start,
the touch order = the nearer level first, cap 12 a side, one per coin & side) -- more trades / quality: the threshold
(q; per year from the previous year's out-of-sample scores, or rolling: the bot coins' out-of-sample scores of the 180
days ending 14 days before the month), the universe (bot coins / all 211: the model never trained on the 84 others),
the side, the exits (hard stop x dATR, take R, hold h, the close-stop TF), the level subset. Scores: the E2-label
walk-forward model (div_lv2_1537_sc.npz). Output: per config n, n/year, R, WR, R by year, R-sum per year."""
import sys, json, glob, numpy as np, warnings, itertools; warnings.filterwarnings("ignore")
sys.argv = ["x"]
from numba import njit
from lv_wf import load_dir, ts
import lv_engine as LE
Dd = load_dir("lv2", LE.FNAMES); fam = Dd["F"][:, 0].astype(int)
LV, J, DT = [], [], []
for fn in sorted(glob.glob("lv2/*.npz")):
    z = np.load(fn)
    if len(z["t"]) == 0: continue
    LV.append(z["lv"]); J.append(z["j"]); DT.append(z["datr"])
LV, J, DATR = np.concatenate(LV), np.concatenate(J).astype(np.int64), np.concatenate(DT)
T, SIDE, SYM, BOT = Dd["T"], Dd["SIDE"], Dd["SYM"], Dd["BOT"]
yr = np.array([int(np.datetime64(int(t), "s").astype("datetime64[Y]").astype(int) + 1970) for t in T])
mo = (T.astype("datetime64[s]").astype("datetime64[M]").astype(int))
z = np.load("htf_long_sc.npz", allow_pickle=True); SC = z["SC"]; THR = z["THR"].item()
HTF = (fam <= 22) & (SIDE > 0) & np.isfinite(SC) & (T >= ts(2022))

from bt_trades import gate_sym
zo = np.load("div_lv2_1537_sc.npz", allow_pickle=True); SCo = zo["SC"]; THRo = zo["THR"].item()
SCn, THRn = SC, THR
def pct(SCx, THRx):
    p = np.full(len(T), np.nan)
    for Y, v in THRx.items():
        m = (yr == Y) & np.isfinite(SCx)
        if m.any(): p[m] = np.searchsorted(np.sort(v), SCx[m]) / len(v)
    return p
Po, Pn = pct(SCo, THRo), pct(SCn, THRn)
BASEM = (fam <= 22) & (SIDE > 0) & (T >= ts(2023)) & BOT & np.isfinite(Po) & np.isfinite(Pn)
RULES = {"старая q0.993": Po >= 0.993, "новая q0.993": Pn >= 0.993,
         "ИЛИ q0.993": (Po >= 0.993) | (Pn >= 0.993), "ИЛИ q0.995": (Po >= 0.995) | (Pn >= 0.995),
         "И q0.98": (Po >= 0.98) & (Pn >= 0.98), "И q0.985": (Po >= 0.985) & (Pn >= 0.985), "И q0.99": (Po >= 0.99) & (Pn >= 0.99),
         "смесь q0.99": (Po + Pn) / 2 >= 0.99, "смесь q0.993": (Po + Pn) / 2 >= 0.993}
cand = np.where(BASEM & np.logical_or.reduce(list(RULES.values())))[0]
print("кандидатов", len(cand), flush=True)
@njit
def wk2(O, H, L, C, Tb, j, s, fill, datr, hard_a, take, hold, kh):
    risk = fill * datr / 100; ssl = fill - s * risk; hsl = fill - s * hard_a * risk; tp = fill + s * take * risk
    n = len(C); e = min(n, j + hold)
    for q in range(e - j):
        b = j + q
        if (s > 0 and L[b] <= hsl) or (s < 0 and H[b] >= hsl):
            x = O[b] if (q > 0 and ((s > 0 and O[b] <= hsl) or (s < 0 and O[b] >= hsl))) else hsl
            return s * (x - fill) / risk - (0.001 + 0.0003 * (q + 1) / 24) * fill / risk, q + 1
        if q > 0 and ((s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp)):
            return s * (tp - fill) / risk - (0.001 + 0.0003 * (q + 1) / 24) * fill / risk, q + 1
        if (Tb[b] + 3600) % (kh * 3600) == 0 and ((s > 0 and C[b] <= ssl) or (s < 0 and C[b] >= ssl)):
            return s * (C[b] - fill) / risk - (0.001 + 0.0003 * (q + 1) / 24) * fill / risk, q + 1
    b = e - 1
    return s * (C[b] - fill) / risk - (0.001 + 0.0003 * (e - j) / 24) * fill / risk, e - j
R = np.full(len(T), np.nan); K = np.zeros(len(T), np.int64); OPEN = np.full(len(T), np.nan); PX = np.full(len(T), np.nan)
for k in sorted(set(SYM[cand])):
    Tb, O, H, L, C, V = LE.load_np(Dd["names"][k])
    for i in cand[SYM[cand] == k]:
        OPEN[i] = O[J[i]]; PX[i] = C[J[i] - 1]
        R[i], K[i] = wk2(O, H, L, C, Tb, int(J[i]), 1, float(LV[i]), float(DATR[i]), 3.0, 3.0, 96, 4)
cand = cand[np.abs(PX[cand] - LV[cand]) / PX[cand] * 100 <= 1.5 * DATR[cand]]
NEAR = (OPEN - LV) / (LV * DATR / 100)
YRS = (ts(2026, 10) - ts(2023)) / (365.25 * 86400)
for nm, rule in RULES.items():
    ii = cand[rule[cand]]
    o = ii[np.lexsort((NEAR[ii], T[ii]))]
    busy, act, sel = {}, [], []
    for i in o:
        t = T[i]
        if busy.get(SYM[i], 0) > t: continue
        act = [a for a in act if a > t]
        if len(act) >= 12: continue
        end = t + int(K[i]) * 3600; busy[SYM[i]] = end; act.append(end); sel.append(i)
    sel = np.array(sel, np.int64); r = R[sel]; y = yr[sel]
    print(f"{nm:16s} n{len(sel):4d} ({len(sel) / YRS:4.0f}/год) {r.mean():+.3f}R WR {(r > 0).mean()*100:.0f}% ΣR/год {r.sum() / YRS:+6.1f} | "
          + " ".join(f"{Y % 100}:{r[y == Y].mean() if (y == Y).any() else float('nan'):+.2f}({(y == Y).sum()})" for Y in range(2023, 2027)), flush=True)
    out = []
    for i in sel:
        gs, scl = gate_sym(Dd["names"][SYM[i]]); lv = float(LV[i]); risk = lv * float(DATR[i]) / 100
        out.append({"s": gs, "d": 1, "t": int(T[i]), "e": lv / scl, "sl": (lv - risk) / scl, "hs": (lv - 3.0 * risk) / scl, "x": int(T[i] + K[i] * 3600), "r": float(R[i])})
    json.dump(out, open(f"htfS_{nm.replace(' ', '_')}.json", "w"))
