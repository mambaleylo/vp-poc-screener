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
QS = (0.95, 0.97, 0.98, 0.985, 0.99, 0.993, 0.995)
def thr_year(q):
    t = np.array([np.quantile(THR[Y], q) if Y in THR else np.inf for Y in range(1970, 2030)]); return t[np.clip(yr - 1970, 0, 59)]
def thr_roll(q):
    out = np.full(len(T), np.inf); ref = HTF & BOT
    for m in np.unique(mo[HTF]):
        m0 = np.datetime64(int(m), "M").astype("datetime64[s]").astype(int)
        w = ref & (T >= m0 - 180 * 86400) & (T < m0 - 14 * 86400)
        v = np.quantile(SC[w], q) if w.sum() >= 2000 else thr_year(q)[np.argmax(mo == m)]
        out[mo == m] = v
    return out
TH = {("год", q): thr_year(q) for q in QS}
TH.update({("скольз", q): thr_roll(q) for q in QS})
qmin = np.minimum(TH[("год", QS[0])], TH[("скольз", QS[0])])
idx = np.where(HTF & (SC >= qmin))[0]
print("кандидатов (q0.98, оба порога)", len(idx), flush=True)
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
EX = [("SMC (2/3R/96/4h)", 2.0, 3.0, 96, 4), ("тейк 2R", 2.0, 2.0, 96, 4), ("тейк 4R", 2.0, 4.0, 96, 4), ("тейк 5R 144ч", 2.0, 5.0, 144, 4),
      ("144ч", 2.0, 3.0, 144, 4), ("72ч", 2.0, 3.0, 72, 4), ("авар 1.5", 1.5, 3.0, 96, 4), ("авар 3", 3.0, 3.0, 96, 4),
      ("закр 1h", 2.0, 3.0, 96, 1), ("закр 1d", 2.0, 3.0, 96, 24), ("тейк 2.5R авар 1.5", 1.5, 2.5, 96, 4)]
R = np.full((len(EX), len(T)), np.nan); K = np.zeros((len(EX), len(T)), np.int64)
OPEN = np.full(len(T), np.nan); PX = np.full(len(T), np.nan)
for k in sorted(set(SYM[idx])):
    Tb, O, H, L, C, V = LE.load_np(Dd["names"][k])
    for i in idx[SYM[idx] == k]:
        OPEN[i] = O[J[i]]; PX[i] = C[J[i] - 1]
        for e_, (_, ha, tk, hd, kh) in enumerate(EX):
            R[e_, i], K[e_, i] = wk2(O, H, L, C, Tb, int(J[i]), int(SIDE[i]), float(LV[i]), float(DATR[i]), ha, tk, hd, kh)
idx = idx[np.abs(PX[idx] - LV[idx]) / PX[idx] * 100 <= 1.5 * DATR[idx]]
NEAR = SIDE * (OPEN - LV) / (LV * DATR / 100)
print("в досягаемости", len(idx), flush=True)
FN = {nm: k for k, nm in enumerate(LE.FAMS)}
SUBS = {"все": np.ones(len(T), bool),
        "без слабых": ~np.isin(fam, [FN[x] for x in ("pdh", "pmh", "pml", "mopen", "yopen", "wopen")]),
        "SMA+BB+pdl/pdm": np.isin(fam, [FN[x] for x in ("pdl", "pdm", "d_sma20", "d_sma50", "d_sma100", "d_sma200", "d_bbu", "d_bbl", "w_sma10", "w_sma20", "w_sma50", "w_bbu", "w_bbl", "pwl", "pwm")])}
YRS = (ts(2026, 10) - ts(2023)) / (365.25 * 86400)
LAST = [None]
def run(mode, q, univ, side, e_, sub):
    th = TH[(mode, q)]
    m = (SC[idx] >= th[idx]) & SUBS[sub][idx] & (T[idx] >= ts(2023))
    if univ == "бот": m &= BOT[idx]
    if univ == "чек": m &= ~BOT[idx]
    if side != 0: m &= SIDE[idx] == side
    ii = idx[m]
    o = ii[np.lexsort((NEAR[ii], T[ii]))]
    busy, act, sel = {}, [], []
    for i in o:
        t = T[i]; key = (SYM[i], SIDE[i])
        if busy.get(key, 0) > t: continue
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == SIDE[i]) >= 12: continue
        end = t + int(K[e_, i]) * 3600; busy[key] = end; act.append((end, SIDE[i])); sel.append(i)
    sel = np.array(sel, np.int64)
    LAST[0] = sel
    if len(sel) == 0: return None
    r = R[e_, sel]; y = yr[sel]
    by = {Y: (r[y == Y].mean() if (y == Y).any() else np.nan, int((y == Y).sum())) for Y in range(2023, 2027)}
    return dict(n=len(sel), nyr=len(sel) / YRS, R=r.mean(), wr=(r > 0).mean(), by=by, sumyr=r.sum() / YRS, minY=min(v[0] for v in by.values() if v[1] >= 5) if any(v[1] >= 5 for v in by.values()) else np.nan,
                minN=min(v[1] for v in by.values()))
def fmt(c, s):
    return (f"{c:62s} n{s['n']:4d} ({s['nyr']:5.0f}/год) {s['R']:+.3f}R WR{s['wr']*100:3.0f}% ΣR/год {s['sumyr']:+6.1f} | "
            + " ".join(f"{Y % 100}:{v[0]:+.2f}({v[1]})" for Y, v in s["by"].items()))

from bt_trades import gate_sym
EXN = {nm: k for k, (nm, *_) in enumerate(EX)}
for nm, mode, q in (("NS985", "скольз", 0.985), ("NS99", "скольз", 0.99)):
    e_ = EXN["авар 3"]; s_ = run(mode, q, "бот", 1, e_, "все"); sel = LAST[0]; out = []
    for i in sel:
        gs, scl = gate_sym(Dd["names"][SYM[i]]); lv = float(LV[i]); risk = lv * float(DATR[i]) / 100
        out.append({"s": gs, "d": 1, "t": int(T[i]), "e": lv / scl, "sl": (lv - risk) / scl, "hs": (lv - 3.0 * risk) / scl, "x": int(T[i] + K[e_, i] * 3600), "r": float(R[e_, i])})
    json.dump(out, open(f"htfL_{nm}_бот.json", "w")); print(nm, len(out), flush=True)
