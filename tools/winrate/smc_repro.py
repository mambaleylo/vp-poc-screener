"""is SMC's deployed model reproducible? smc_export.py's recipe (new_ind): the bot coins' SMC touches (lv2 fam >= 33), the
label E2 clipped to [-1.2, 6], 2 LightGBM (seeds 0, 1) on everything closed 14 days before 2026 -> its scores vs the
deployed trees on the 2026 touches: the correlation, the picks over the deployed threshold, the R of the picks"""
import os, sys, json, numpy as np, lightgbm as lgb, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "new_ind")); sys.path += [os.path.join(HERE, "..", "zones_model"), os.path.join(HERE, "..", "neuro_model")]
import types; sys.modules.setdefault("nx_h", types.SimpleNamespace(pain=None))   # lv_wf imports nx_h only for pain (its data load is not needed here)
from lv_wf import load_dir, ts
import lv_engine as LE, treevec as TV
M = json.load(open(os.path.join(HERE, "..", "..", "vp_smc_model.json")))
print("deployed:", {k: M.get(k) for k in ("ver", "thr", "q")}, "feats same:", M.get("feats") == LE.FNAMES, flush=True)
Dd = load_dir("lv2", LE.FNAMES)
F = Dd["F"]; fam = F[:, 0].astype(int); T = Dd["T"]
y = np.nan_to_num(Dd["R"][2], nan=0.0).clip(-1.2, 6.0)
tr = (fam >= 33) & Dd["BOT"] & (T < ts(2026) - 14 * 86400)
pr = dict(n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=300, subsample=0.7, subsample_freq=1, colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
te = np.flatnonzero((fam >= 33) & Dd["BOT"] & (T >= ts(2026)))
a = np.mean([lgb.LGBMRegressor(random_state=s, **pr).fit(F[tr], y[tr]).predict(F[te]) for s in range(2)], axis=0)
mods = M["models"] if isinstance(M["models"], list) else list(M["models"].values())
b = TV.model_score(mods, F[te].astype(float))
thr = float(M["thr"] if not isinstance(M["thr"], dict) else list(M["thr"].values())[0])
sa, sb = a >= thr, b >= thr
R = Dd["R"][2][te]
f_ = lambda m_: f"{np.nanmean(R[m_]):+.3f}R ({int(m_.sum())})" if m_.any() else "—"
print(f"обучающих {int(tr.sum())}, касаний 2026 {len(te)}, корреляция оценок {np.corrcoef(a, b)[0, 1]:.4f}; выше порога бота: пересборка {f_(sa)}, бот {f_(sb)}, общих {int((sa & sb).sum())}", flush=True)
print("smc repro done", flush=True)
