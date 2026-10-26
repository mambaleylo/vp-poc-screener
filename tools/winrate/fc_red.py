"""the opposite-side classic without the 30-day z features the live bot cannot rebuild (Binance keeps 30 days of the
long/short, taker and top-trader statistics): ls_z, tk_z, top_z zeroed; the walk-forward model on the flipped E2 label
re-trained; the rolling-threshold selection (180 / 240 days, q 0.995 / 0.997) vs the full-feature one"""
import sys, json, glob, numpy as np, warnings; warnings.filterwarnings("ignore")
sys.argv = ["x"]
import lv_engine as LE, ev3_engine as E3, ev2_engine as E2
from lv_wf import load_dir, scores, ts
Dd = load_dir("ev3", E3.FNAMES); T, SIDE, SYM, BOT = Dd["T"], Dd["SIDE"], Dd["SYM"], Dd["BOT"]
J, DA = [], []
for fn in sorted(glob.glob("ev3/*.npz")):
    z = np.load(fn)
    if len(z["t"]) == 0: continue
    J.append(z["j"]); DA.append(z["datr"])
J, DA = np.concatenate(J).astype(np.int64), np.concatenate(DA)
try:
    z = np.load("fc_RF.npz"); RF, KF = z["RF"], z["KF"]
except FileNotFoundError:
    RF = np.full(len(T), np.nan, np.float32); KF = np.zeros(len(T), np.int32)
    idx = np.where(T >= ts(2019))[0]
    for k in sorted(set(SYM[idx])):
        Tb, O, H, L, C, V = LE.load_np(Dd["names"][k])
        for i in idx[SYM[idx] == k]:
            jE = int(J[i]) + 1
            if jE < len(C): RF[i], KF[i] = LE.simp(O, H, L, C, jE, -int(SIDE[i]), float(O[jE]), float(DA[i]), 1.0, 3.0, 72, 0.0, 0.0)
    np.savez("fc_RF.npz", RF=RF, KF=KF)
drop = [E2.FNAMES.index(c) for c in ("ls_z", "tk_z", "top_z")]
Dd["F"][:, drop] = 0.0
Dd["R"] = np.vstack([Dd["R"], RF[None, :]]); Dd["K"] = np.vstack([Dd["K"], KF[None, :]]); ef = Dd["R"].shape[0] - 1
SC, THR = scores(Dd, ef, mask=(T >= ts(2021)), seeds=2)
np.savez("fc_red_sc.npz", SC=SC, THR=np.array(THR, dtype=object))
print("готово: оценки без 3 признаков", flush=True)
