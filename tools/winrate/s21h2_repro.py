"""⚡ 2h: the deployed close2h model rebuilt with the restored research engine (s21h2_engine.py -> s21h2/, s24_featall.py ->
f2_s21h2/) and s26_mix.py's recipe: fam d2, exit E1 (take 1 / stop 2 ATR / 32 bars) clipped to +-1.5, 10 seeds on the 28
features + 10 on the 28 + 5 daily ones, the train coins (sorted names, every 3rd from the 3rd = check) with events before
2026 - 3 days (the 2026 model of the walk-forward = the deployed one, trained_to 2025-12-29). Then vs the deployed trees:
identical?, the scores' correlation, the top 1% overlap and R on the research's 2026 events (all coins)"""
import os, sys, json, glob, numpy as np, lightgbm as lgb, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.append(os.path.join(HERE, "..", "zones_model"))
os.environ.setdefault("TFH", "2")
import s21h2_engine as E, treevec as TV
from s15_wf import load
from lgbpure import export
import calendar
ts = lambda y, m=1, d=1: calendar.timegm((y, m, d, 0, 0, 0))
M = json.load(open(os.path.join(HERE, "..", "..", "vp_dlm_model.json"))); S = [s for s in M["streams"] if s["name"] == "close2h"][0]
fi = E.FAMS.index("d2"); EX = 1
D = load("s21h2", [fi])
F2, t2 = [], []
for f in sorted(glob.glob("s21h2/*.npz")):
    z = np.load(f); m = z["fam"] == fi
    if not m.any(): continue
    g = np.load(f"f2_s21h2/{os.path.basename(f)}"); F2.append(g["F2"][m]); t2.append(g["t"][m])
F2 = np.concatenate(F2); t2 = np.concatenate(t2); assert (t2 == D["t"]).all()
T = D["t"]; TR = ~D["chk"]; y = np.clip(D["R"][EX], -1.5, 1.5)
X1 = D["F"]; X2 = np.concatenate([D["F"], F2[:, [0, 1, 2, 5, 8]]], axis=1)
pr = dict(n_estimators=300, learning_rate=0.05, num_leaves=63, min_child_samples=1000, subsample=0.7, subsample_freq=1,
          colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
tr0 = np.flatnonzero(TR & (T < ts(2026) - 3 * 86400))
print(f"событий d2: {len(T)} ({len(D['names'])} монет, обучающих {len(set(D['sym'][tr0]))}); для обучения {len(tr0)}; первое {np.datetime64(int(T.min()), 's')}", flush=True)
te = np.flatnonzero(T >= ts(2026)); models = []; sc = np.zeros(len(te))
for X in (X1, X2):
    for seed in range(10):
        rng = np.random.default_rng(seed); tr = tr0 if len(tr0) <= 800000 else rng.choice(tr0, 800000, replace=False)
        m = lgb.LGBMRegressor(random_state=seed, **pr).fit(X[tr], y[tr]); models.append(export(m.booster_, E.FNAMES + ["d_e20", "d_e50", "d_rsi", "d_pos20", "b_d_e50"][:X.shape[1] - 28])["trees"])
        sc += m.predict(X[te]) / 20
same = [json.dumps(a) == json.dumps(b) for a, b in zip(models, S["models"])]
print(f"деревья совпали: {sum(same)}/20 {''.join('1' if x else '0' for x in same)}", flush=True)
dep = TV.model_score(S["models"], X2[te].astype(float))
print(f"корреляция оценок 2026 {np.corrcoef(dep, sc)[0, 1]:.4f}, макс. разница {np.abs(dep - sc).max():.4f}; выше порога бота {S['thr']}: бот {(dep >= S['thr']).sum()} / пересборка {(sc >= S['thr']).sum()}", flush=True)
r = D["R"][EX][te]; sd = D["side"][te]
for q in (0.99, 0.97):
    a, b = dep >= np.quantile(dep, q), sc >= np.quantile(sc, q)
    print(f"верхние {100 - q * 100:.0f}%: общих {(a & b).sum() / a.sum() * 100:.0f}%; R бот {r[a].mean():+.3f} ({a.sum()}) | пересборка {r[b].mean():+.3f} ({b.sum()}); "
          f"лонги бот {r[a & (sd > 0)].mean():+.3f} / пересборка {r[b & (sd > 0)].mean():+.3f}; шорты бот {r[a & (sd < 0)].mean():+.3f} / пересборка {r[b & (sd < 0)].mean():+.3f}", flush=True)
json.dump({"models": models}, open("s21h2_models.json", "w"))
print("s21h2 repro done", flush=True)
