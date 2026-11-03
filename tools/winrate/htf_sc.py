"""📏 HTF lab from scratch (the round of v0.99.773): the yearly walk-forward scores of both deployed models on the clean 2020-
candles' events (lv2 of tools/winrate/smclab: fam <= 22 = the HTF levels), the recipe of htf_export.py:
  "o" = all HTF levels, both sides, label E2 (stop 1 dATR, take 3R, 72 h)   (was div_lv2_1537_sc.npz)
  "n" = the long HTF touches 2019+, label = the traded exit (htf_relabel.py: the soft stop 1 dATR at a 4h close, the hard
        3 dATR, take 3R, 96 h)                                             (was htf_long_sc.npz)
both trained on the 127 bot coins only, 2 seeds, 14 days embargo; thr per year = the previous year's out-of-sample scores
-> htf_o_sc.npz, htf_n_sc.npz (in the lab dir; LV_D1H = the events' candles)"""
import sys, types, numpy as np, warnings; warnings.filterwarnings("ignore")
sys.modules.setdefault("nx_h", types.SimpleNamespace(pain=None))
import glob
from lv_wf import load_dir, scores, ts
import lv_engine as LE
from htf_relabel_wk import wk2
Dd = load_dir("lv2", LE.FNAMES); fam = Dd["F"][:, 0].astype(int)
LV, J, DT = [], [], []
for fn in sorted(glob.glob("lv2/*.npz")):
    z = np.load(fn)
    if len(z["t"]) == 0: continue
    LV.append(z["lv"]); J.append(z["j"]); DT.append(z["datr"])
LV, J, DATR = np.concatenate(LV), np.concatenate(J).astype(np.int64), np.concatenate(DT)
T, SIDE, SYM = Dd["T"], Dd["SIDE"], Dd["SYM"]
SCo, THRo = scores(Dd, 2, mask=fam <= 22, seeds=2)
np.savez("htf_o_sc.npz", SC=SCo, THR=np.array(THRo, dtype=object)); print("o done", flush=True)
LONG = (fam <= 22) & (SIDE > 0) & (T >= ts(2019)) & np.isfinite(DATR)
RL = np.full(len(T), np.nan); KL = np.zeros(len(T), np.int64); ii = np.where(LONG)[0]
for k in sorted(set(SYM[ii])):
    Tb, O, H, L, C, V = LE.load_np(Dd["names"][k])
    for i in ii[SYM[ii] == k]:
        RL[i], KL[i] = wk2(O, H, L, C, Tb, int(J[i]), 1, float(LV[i]), float(DATR[i]), 3.0, 3.0, 96, 4)
print("лонг-событий", len(ii), "ср.R метки", float(np.nanmean(RL[ii])), flush=True)
Dd["R"] = np.vstack([Dd["R"], RL[None, :]]); Dd["K"] = np.vstack([Dd["K"], KL[None, :]])
SCn, THRn = scores(Dd, Dd["R"].shape[0] - 1, mask=LONG, seeds=2)
np.savez("htf_n_sc.npz", SC=SCn, THR=np.array(THRn, dtype=object), RL=RL, KL=KL)
print("htf sc done", flush=True)
