"""SMC 8h/12h (lv8 fam 6..17: FVG / swing / OB on 8h and 12h) as its own stream on the bot's pipeline: its walk-forward
model (SMC8h12h_sc.npz, E2), q of the previous year's OOS scores, the reach filter |px - lv| <= 1.5 dATR, the nearer level
first, cap 12 a side, one per coin & side; exits as the deployed SMC (the soft stop 1 dATR on a 4h close, hard 2 dATR,
take 3R, 96 h) or E2 (the 1 dATR stop by touch, 3R, 72 h). Bot coins (lists saved) / check coins."""
import sys, json, glob, numpy as np, warnings; warnings.filterwarnings("ignore")
CHK = "chk" in sys.argv; sys.argv = ["x"]
from numba import njit
from lv_wf import load_dir, ts
import lv8_engine as L8, lv_engine as LE
from bt_trades import gate_sym
Dd = load_dir("lv8", L8.FNAMES); fam = Dd["F"][:, 0].astype(int); T, SIDE, SYM, BOT = Dd["T"], Dd["SIDE"], Dd["SYM"], Dd["BOT"]
LV, J, DT = [], [], []
for fn in sorted(glob.glob("lv8/*.npz")):
    z = np.load(fn)
    if len(z["t"]) == 0: continue
    LV.append(z["lv"]); J.append(z["j"]); DT.append(z["datr"])
LV, J, DATR = np.concatenate(LV), np.concatenate(J).astype(np.int64), np.concatenate(DT)
z = np.load("SMC8h12h_sc.npz", allow_pickle=True); SC, THR = z["SC"], z["THR"].item()
assert len(SC) == len(T)
yr = np.array([int(np.datetime64(int(t), "s").astype("datetime64[Y]").astype(int) + 1970) for t in T])
exec(open("htf_x2.py").read().split("@njit\ndef wk2")[1].split("def pipeline")[0].join(["@njit\ndef wk2", ""]))
BARS = {}
def bars_of(k):
    if k not in BARS: BARS.clear(); BARS[k] = LE.load_np(Dd["names"][k])
    return BARS[k]
M = ((fam >= 6) & (fam <= 17)) & (BOT if not CHK else ~BOT) & (T >= ts(2022))
def pipeline(nm, q, EXT):
    thr = np.array([np.quantile(THR[Y], q) if Y in THR else np.inf for Y in range(1970, 2030)])
    idx = np.where(M & np.isfinite(SC) & (SC >= thr[np.clip(yr - 1970, 0, 59)]))[0]
    OPEN = np.full(len(T), np.nan); PX = np.full(len(T), np.nan); R = np.full(len(T), np.nan); K = np.zeros(len(T), np.int64)
    for k in sorted(set(SYM[idx])):
        Tb, O, H, L, C, V = bars_of(k)
        for i in idx[SYM[idx] == k]:
            OPEN[i] = O[J[i]]; PX[i] = C[J[i] - 1]
            R[i], K[i], _, _ = wk2(O, H, L, C, Tb, int(J[i]), int(SIDE[i]), float(LV[i]), float(DATR[i]), EXT[0], EXT[1], EXT[2], EXT[3])
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
    print(f"{nm:40s} сделок {len(sel):4d} {r.mean():+.3f}R WR {np.mean(r > 0)*100:.0f}% лонг {int((SIDE[sel] > 0).sum())} {r[SIDE[sel] > 0].mean():+.2f} шорт {r[SIDE[sel] < 0].mean():+.2f} | "
          + " ".join(f"{Y % 100}:{r[y == Y].mean():+.2f}({(y == Y).sum()})" for Y in range(2022, 2027) if (y == Y).any()), flush=True)
    if not CHK:
        out = []
        for i in sel:
            gs, scl = gate_sym(Dd["names"][SYM[i]]); s = int(SIDE[i]); lv = float(LV[i]); risk = lv * float(DATR[i]) / 100
            out.append({"s": gs, "d": s, "t": int(T[i]), "e": lv / scl, "sl": (lv - s * risk) / scl, "hs": (lv - s * EXT[0] * risk) / scl, "x": int(T[i] + K[i] * 3600), "r": float(R[i])})
        json.dump(out, open(f"smc812_{nm.split()[0]}.json", "w"))
print("== монеты", "контрольные" if CHK else "бота", flush=True)
for q in (0.993, 0.995):
    pipeline(f"S{q} выходы как SMC в боте", q, (2.0, 3.0, 96, 4))
    pipeline(f"E{q} E2 (стоп касанием 1, 3R, 72ч)", q, (1.0, 3.0, 72, 4))
