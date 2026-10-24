"""SMC walk-forward scores with the model trained on all 211 coins (was the 127 'bot' coins), the same recipe (lv_wf.scores,
exit E2, yearly, 14 days embargo) -> smc_sc211.npz"""
import numpy as np, warnings; warnings.filterwarnings("ignore")
from lv_wf import *
import lv_engine as LE
Dd = load_dir("lv2", LE.FNAMES)
fam = Dd["F"][:, 0].astype(int)
BOT0 = Dd["BOT"].copy(); Dd["BOT"] = np.ones(len(BOT0), bool)
SC, THR = scores(Dd, 2, mask=fam >= 33)
np.savez("smc_sc211.npz", SC=SC, THR=np.array(THR, dtype=object))
print("done", np.isfinite(SC).sum())
