"""SMC v2: ONE model over the deployed SMC levels (lv2 fam >= 33: FVG / swing / OB on 4h / 1d / 1w) plus the same
structures on 8h / 12h (lv8 fam 6..17 -> 106..117), trained as the deployed one (E2 label, the bot coins, yearly walk-
forward, thr = q of the previous year's out-of-sample scores), then the deployed pipeline: the bot's reach filter
(|px - lv| <= 1.5 dATR at the hour's start), the touch order (the nearer level first), cap 12 a side, one per coin &
side, the exits as v0.99.709 (the soft stop 1 dATR on a 4h close, the hard 2 dATR, take 3R, 96 h). The control: the
deployed model's scores (smc_sc.npz) through the same code -> must give the deployed list (~317 trades, ~+0.9R)."""
import sys, json, glob, os, numpy as np, warnings; warnings.filterwarnings("ignore")
sys.argv = ["x"]
from numba import njit
from lv_wf import load_dir, scores, ts
import lv_engine as LE
from bt_trades import gate_sym
def part(dr, fam_off, keep):
    D_ = load_dir(dr, LE.FNAMES); fm = D_["F"][:, 0].astype(int)
    LV, J, DT = [], [], []
    for fn in sorted(glob.glob(f"{dr}/*.npz")):
        z = np.load(fn)
        if len(z["t"]) == 0: continue
        LV.append(z["lv"]); J.append(z["j"]); DT.append(z["datr"])
    D_["LV"], D_["J"], D_["DATR"] = np.concatenate(LV), np.concatenate(J).astype(np.int64), np.concatenate(DT)
    D_["FAM"] = fm + fam_off; D_["F"][:, 0] = D_["FAM"]; D_["KEEP"] = keep(fm)
    return D_
A = part("lv2", 0, lambda f: np.ones(len(f), bool))
B = part("lv8", 100, lambda f: np.zeros(len(f), bool))
NAMES = sorted(set(A["names"]) | set(B["names"])); nid = {s: k for k, s in enumerate(NAMES)}
Dd = {}
for k_ in ("T", "BOT", "SIDE", "F", "LV", "J", "DATR", "FAM"):
    Dd[k_] = np.concatenate([A[k_][A["KEEP"]] if A[k_].ndim == 1 else A[k_][A["KEEP"]], B[k_][B["KEEP"]]])
for k_ in ("R", "K"):
    Dd[k_] = np.concatenate([A[k_][:, A["KEEP"]], B[k_][:, B["KEEP"]]], axis=1)
Dd["SYM"] = np.concatenate([np.array([nid[A["names"][s]] for s in A["SYM"][A["KEEP"]]]), np.array([nid[B["names"][s]] for s in B["SYM"][B["KEEP"]]])])
Dd["names"] = NAMES
Dd["SYM"] = Dd["SYM"].astype(np.int64)
nA = int(A["KEEP"].sum())
T, SIDE, SYM, LV, J, DATR, fam = Dd["T"], Dd["SIDE"], Dd["SYM"], Dd["LV"], Dd["J"], Dd["DATR"], Dd["FAM"]
yr = np.array([int(np.datetime64(int(t), "s").astype("datetime64[Y]").astype(int) + 1970) for t in T]); Dd["YR"] = yr
OLD = (fam >= 33) & (fam < 100); NEW = fam >= 100
print("events: deployed fams", int(OLD.sum()), "8h/12h", int(NEW.sum()), flush=True)
# control: the deployed scores (on the lv2 rows, the same order as load_dir("lv2"))
z = np.load("smc_sc.npz", allow_pickle=True); SC1 = np.full(len(T), np.nan); SC1[:nA] = z["SC"]; THR1 = z["THR"].item()
if False:
    z = np.load("smcv2_sc.npz", allow_pickle=True); SC2 = z["SC"]; THR2 = z["THR"].item()
else:
    pass
BARS = {}
def bars_of(k):
    if k not in BARS:
        BARS.clear(); BARS[k] = LE.load_np(NAMES[k])
    return BARS[k]
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
def pipeline(nm, SC, THR, q, mask):
    thr = np.array([np.quantile(THR[Y], q) if Y in THR else np.inf for Y in range(1970, 2030)])
    idx = np.where(mask & Dd["BOT"] & np.isfinite(SC) & (SC >= thr[np.clip(yr - 1970, 0, 59)]) & (T >= ts(2022)))[0]
    OPEN = np.full(len(T), np.nan); PX = np.full(len(T), np.nan); R = np.full(len(T), np.nan); K = np.zeros(len(T), np.int64); EX = np.zeros(len(T)); KD = np.zeros(len(T), np.int64)
    for k in sorted(set(SYM[idx])):
        Tb, O, H, L, C, V = bars_of(k)
        for i in idx[SYM[idx] == k]:
            OPEN[i] = O[J[i]]; PX[i] = C[J[i] - 1]
            R[i], K[i], KD[i], EX[i] = wk2(O, H, L, C, Tb, int(J[i]), int(SIDE[i]), float(LV[i]), float(DATR[i]), 2.0, 3.0, 96, 4)
    idx = idx[np.abs(PX[idx] - LV[idx]) / PX[idx] * 100 <= 1.5 * DATR[idx]]
    NEAR = SIDE * (OPEN - LV) / (LV * DATR / 100)
    o = idx[np.lexsort((NEAR[idx], T[idx]))]
    busy, act, sel = {}, [], []
    for i in o:
        t = T[i]; key = (SYM[i], SIDE[i])
        if busy.get(key, 0) > t: continue
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == SIDE[i]) >= 12: continue
        end = t + int(K[i]) * 3600; busy[key] = end; act.append((end, SIDE[i])); sel.append(i)
    sel = np.array(sel, np.int64); r = R[sel]; y = yr[sel]
    print(f"{nm:34s} сделок {len(sel):4d} {r.mean():+.3f}R WR {np.mean(r > 0)*100:.0f}% из них 8h/12h {int(NEW[sel].sum())} ({R[sel][NEW[sel]].mean() if NEW[sel].any() else 0:+.2f}R) | "
          + " ".join(f"{Y % 100}:{r[y == Y].mean():+.2f}({(y == Y).sum()})" for Y in range(2022, 2027) if (y == Y).any()), flush=True)
    out = []
    for i in sel:
        gs, scl = gate_sym(NAMES[SYM[i]]); s = int(SIDE[i]); lv = float(LV[i]); risk = lv * float(DATR[i]) / 100
        out.append({"s": gs, "d": s, "t": int(T[i]), "e": lv / scl, "sl": (lv - s * risk) / scl, "hs": (lv - s * 2.0 * risk) / scl,
                    "x": int(T[i] + K[i] * 3600), "r": float(R[i]), "new": bool(NEW[i])})
    json.dump(out, open(f"htfx_{nm.split()[0]}.json", "w"))
    return out
z = np.load("div_lv2_1537_sc.npz", allow_pickle=True); SCH = np.full(len(T), np.nan); SCH[:nA] = z["SC"]; THRH = z["THR"].item()
HTF = fam <= 22
pipeline("v1_q0.993 (контроль, боевой)", SC1, THR1, 0.993, OLD)
for q in (0.99, 0.993, 0.995, 0.997):
    pipeline(f"htf_q{q} (HTF-уровни, выходы SMC)", SCH, THRH, q, HTF)
