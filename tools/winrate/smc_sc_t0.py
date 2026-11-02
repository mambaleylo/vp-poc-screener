"""SMC like the bot trades it: the events at ANY touch of a level (lv_engine LV_TOUCH=0 -> lv2_t0; the lab's lv2 wanted the
hour 0.1% past it, the bot fires on every touch) scored by the yearly walk-forward models trained exactly as the deployed
recipe (lv_wf.scores: the 0.1% events of the 127 bot coins, label E2, 2 seeds, 14 days embargo); the thresholds = the
previous year's out-of-sample scores of those training events (as the deployed thr) -> smc_sc_t0.npz (run in the lab dir)"""
import sys, types, numpy as np, lightgbm as lgb, warnings; warnings.filterwarnings("ignore")
sys.modules.setdefault("nx_h", types.SimpleNamespace(pain=None))
from lv_wf import load_dir, ts
import lv_engine as LE
A = load_dir("lv2", LE.FNAMES); B = load_dir("lv2_t0", LE.FNAMES)
fa, fb = A["F"][:, 0].astype(int) >= 33, B["F"][:, 0].astype(int) >= 33
y = np.nan_to_num(A["R"][2], nan=0.0).clip(-1.2, 6.0)
pr = dict(n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=300, subsample=0.7, subsample_freq=1,
          colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
SCA = np.full(len(A["T"]), np.nan); SCB = np.full(len(B["T"]), np.nan); THR = {}
for Y in (2022, 2023, 2024, 2025, 2026):
    tr = fa & A["BOT"] & (A["T"] < ts(Y) - 14 * 86400)
    ms = [lgb.LGBMRegressor(random_state=s_, **pr).fit(A["F"][tr], y[tr]) for s_ in range(2)]
    sa = np.mean([m.predict(A["F"]) for m in ms], axis=0); sb = np.mean([m.predict(B["F"]) for m in ms], axis=0)
    ta = fa & (A["T"] >= ts(Y)) & (A["T"] < ts(Y + 1)); tb = fb & (B["T"] >= ts(Y)) & (B["T"] < ts(Y + 1))
    SCA[ta] = sa[ta]; SCB[tb] = sb[tb]
    ref = fa & A["BOT"] & (A["T"] >= ts(Y - 1)) & (A["T"] < ts(Y) - 14 * 86400)
    prev = ref & np.isfinite(SCA)
    THR[Y] = SCA[prev] if prev.sum() >= 200 else sa[ref]
    print(Y, "обучено", int(tr.sum()), flush=True)
np.savez("smc_sc_t0.npz", SC=SCB, SCA=SCA, THR=np.array(THR, dtype=object))
print("sc t0 done", int(np.isfinite(SCB).sum()), flush=True)
