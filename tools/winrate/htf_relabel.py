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
z = np.load("div_lv2_1537_sc.npz", allow_pickle=True); SC = z["SC"]; THR = z["THR"].item()
HTF = (fam <= 22) & np.isfinite(SC) & (T >= ts(2022))

from lv_wf import scores
# the label = the deployed-style exit of the stream (hard 3 dATR, take 3R, 96h, the soft stop on a 4h close), LONGS only
LONG = (fam <= 22) & (SIDE > 0) & (T >= ts(2019)) & np.isfinite(DATR)
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
RL = np.full(len(T), np.nan); KL = np.zeros(len(T), np.int64)
ii = np.where(LONG)[0]
for k in sorted(set(SYM[ii])):
    Tb, O, H, L, C, V = LE.load_np(Dd["names"][k])
    for i in ii[SYM[ii] == k]:
        RL[i], KL[i] = wk2(O, H, L, C, Tb, int(J[i]), 1, float(LV[i]), float(DATR[i]), 3.0, 3.0, 96, 4)
print("лонг-событий", len(ii), "ср.R метки", np.nanmean(RL[ii]), flush=True)
Dd["R"] = np.vstack([Dd["R"], RL[None, :]]); Dd["K"] = np.vstack([Dd["K"], KL[None, :]])
eL = Dd["R"].shape[0] - 1
SCn, THRn = scores(Dd, eL, mask=LONG, seeds=2)
np.savez("htf_long_sc.npz", SC=SCn, THR=np.array(THRn, dtype=object), RL=RL, KL=KL)
print("готово", flush=True)
