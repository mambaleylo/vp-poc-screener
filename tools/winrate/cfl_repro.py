"""is Классика's deployed model reproducible? cfl_export.py's recipe on the ev3 events rebuilt from scratch (ev3_engine with the
lab-store's 1h, metrics, funding -> fc_red.py's flipped label RF): 2 LightGBM (seeds 0, 1) on the bot coins' events 2021 ..
2026 - 14 days, ls_z / tk_z / top_z zeroed -> vs the deployed trees: the trees, the scores on the 2026 events, the top 0.3%
picks (the rule's q 0.997) and their R (longs only, the rule's side)"""
import os, sys, json, numpy as np, lightgbm as lgb, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "new_ind")); sys.path += [os.path.join(HERE, "..", "zones_model"), os.path.join(HERE, "..", "neuro_model")]
import types; sys.modules.setdefault("nx_h", types.SimpleNamespace(pain=None))
sys.argv = ["x"]
from lv_wf import load_dir, ts
import ev3_engine as E3, ev2_engine as E2, treevec as TV
from lgbpure import export
M = json.load(open(os.path.join(HERE, "..", "..", "vp_cfl_model.json")))
print("feats same:", M["feats"] == E2.FNAMES, flush=True)
Dd = load_dir("ev3", E3.FNAMES); T, SIDE, BOT, F = Dd["T"], Dd["SIDE"], Dd["BOT"], Dd["F"]
F[:, [E2.FNAMES.index(c) for c in M["zero"]]] = 0.0
RF = np.load("fc_RF.npz")["RF"]
MASK = T >= ts(2021); CUT = ts(2026) - 14 * 86400
pr = dict(n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=300, subsample=0.7, subsample_freq=1, colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
y = np.nan_to_num(RF, nan=0.0).clip(-1.2, 6.0); tr = MASK & BOT & (T < CUT)
print(f"событий {len(T)}, для обучения {int(tr.sum())}, последнее обучающее {np.datetime64(int(T[tr].max()), 's')} (у бота trained_to {np.datetime64(M['trained_to'], 's')})", flush=True)
te = np.flatnonzero(MASK & BOT & (T >= ts(2026)))
trees, a = [], np.zeros(len(te))
for s in range(2):
    m = lgb.LGBMRegressor(random_state=s, **pr).fit(F[tr], y[tr]); trees.append(export(m.booster_, E2.FNAMES)["trees"]); a += m.predict(F[te]) / 2
print(f"деревья совпали: {sum(json.dumps(x) == json.dumps(z) for x, z in zip(trees, M['models']))}/2", flush=True)
b = TV.model_score(M["models"], F[te].astype(float))
print(f"корреляция оценок 2026 {np.corrcoef(a, b)[0, 1]:.4f}, макс. разница {np.abs(a - b).max():.4f}", flush=True)
r = RF[te]; lg = SIDE[te] < 0   # the flipped label: the trade is opposite the event's side; the rule keeps the longs (side 1 of the trade)
for q in (0.997, 0.99, 0.97):
    A, B = a > np.quantile(a, q), b > np.quantile(b, q)
    print(f"верхние {100 - q * 100:.1f}%: общих {(A & B).sum() / max(1, B.sum()) * 100:.0f}%; R бот {np.nanmean(r[B]):+.3f} ({B.sum()}) | пересборка {np.nanmean(r[A]):+.3f} ({A.sum()})", flush=True)
print("cfl repro done", flush=True)
