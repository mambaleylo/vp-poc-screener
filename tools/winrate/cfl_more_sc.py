"""Классика on 100 more coins (the user: "подгрузи ещё монет 100 и проверь на них, может так простои закроются"): their ev3
events (ev3x/) scored by the same walk-forward models (lv_wf.scores: a yearly LightGBM on the 127 bot coins only — the new
coins never trained on), appended after ev3's events -> fc_red_sc_x.npz (the old part = fc_red_sc.npz exactly; the rebuilt
old part's correlation with it printed as the check). usage (tools/winrate): run in run_cfl_more.sh"""
import sys, numpy as np
sys.argv = ["x"]
import ev3_engine as E3, ev2_engine as E2
from lv_wf import load_dir, scores, ts
Dd = load_dir("ev3", E3.FNAMES); Dx = load_dir("ev3x", E3.FNAMES); n0 = len(Dd["T"])
for k in ("T", "BOT", "SIDE", "F"): Dd[k] = np.concatenate([Dd[k], Dx[k]])
Dd["SYM"] = np.concatenate([Dd["SYM"], Dx["SYM"] + len(Dd["names"])]); Dd["names"] = Dd["names"] + Dx["names"]
z = np.load("fc_RF.npz"); RF = np.concatenate([z["RF"], np.full(len(Dx["T"]), np.nan, np.float32)]); KF = np.concatenate([z["KF"], np.zeros(len(Dx["T"]), np.int32)])
Dd["R"] = np.vstack([np.concatenate([Dd["R"], Dx["R"]], axis=1), RF[None, :]]); Dd["K"] = np.vstack([np.concatenate([Dd["K"], Dx["K"]], axis=1), KF[None, :]])
Dd["F"][:, [E2.FNAMES.index(c) for c in ("ls_z", "tk_z", "top_z")]] = 0.0
print(f"событий: старых {n0}, новых {len(Dx['T'])} на {len(Dx['names'])} монетах; обучающих (монеты бота) {int(Dd['BOT'].sum())}", flush=True)
SC2, THR = scores(Dd, Dd["R"].shape[0] - 1, mask=(Dd["T"] >= ts(2021)), seeds=2)
old = np.load("fc_red_sc.npz", allow_pickle=True)["SC"]; ok = np.isfinite(old) & np.isfinite(SC2[:n0])
print(f"проверка: старые события пересчитаны — корреляция {np.corrcoef(old[ok], SC2[:n0][ok])[0, 1]:.4f}, совпало точно {np.mean(np.abs(old[ok] - SC2[:n0][ok]) < 1e-6) * 100:.0f}%", flush=True)
np.savez("fc_red_sc_x.npz", SC=np.concatenate([old, SC2[n0:]]).astype(np.float32))
print("cfl more sc done", flush=True)
