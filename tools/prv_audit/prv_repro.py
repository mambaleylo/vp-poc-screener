"""is P/R's deployed model reproducible (the user: "в истории всё пересмотреть и сопоставить")? prv_export3.py's export
recipe on the rebuilt events (prv_ev2.py, with the funding): the 127 research coins, the 1h and 4h events, the label
stop 1.5 ATR / take 3R clipped to [-1.5, 4], 3 LightGBM per side (seeds 0..2) on the 24 months before the data's end
(a 10-day gap) -> its scores vs the deployed trees' scores on the last 12 months' events: the correlation, the overlap
of the chosen (over each one's threshold)"""
import os, sys, re, glob, datetime as dt, json, numpy as np, lightgbm as lgb
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "neuro_model")); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "winrate"))
import nx_feat, treevec as TV
from prv_ev import STOPS, TAKES, BAND_NAMES
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
NAMES = BAND_NAMES + nx_feat.NAMES
M = json.load(open(os.path.join(HERE, "..", "..", "vp_prv_model.json")))
assert M["feats"] == NAMES, "the deployed feature order differs"
src = open(os.path.join(HERE, "..", "..", "vp_poc_screener.py")).read()
C127 = re.search(r'RESEARCH_COINS_127 = tuple\("""(.*?)"""', src, re.S).group(1).split()
syms = sorted({x for c in C127 for x in (c.replace("_USDT", "") + "USDT", "1000" + c.replace("_USDT", "") + "USDT") if os.path.exists(f"{ST}/prv_ev/{x}.npz")})
Xs, Ys, Ts = [], [], []
for s in syms:
    z = np.load(f"{ST}/prv_ev/{s}.npz")
    if len(z["t"]): Xs.append(z["X"]); Ys.append(z["Y"]); Ts.append(z["t"])
X = np.concatenate(Xs); Y = np.concatenate(Ys); T = np.concatenate(Ts)
Y = np.where(np.abs(Y) > 20, np.nan, Y); lab = Y[:, STOPS.index(1.5), TAKES.index(3.0)]
SD = X[:, 1].astype(int)
def month_add(t, k):
    d = dt.datetime.fromtimestamp(int(t), dt.timezone.utc); m = d.month - 1 + k
    return int(dt.datetime(d.year + m // 12, m % 12 + 1, 1, tzinfo=dt.timezone.utc).timestamp())
tmax = int(M["trained_to"]); GAP = 10 * 86400
full = (T < tmax - GAP) & (T >= month_add(tmax, -24) - GAP); last = (T >= tmax - 365 * 86400) & (T <= tmax)
print(f"coins {len(syms)}, events {len(T)}, data to {dt.datetime.utcfromtimestamp(int(T.max()))}, deployed trained_to {dt.datetime.utcfromtimestamp(tmax)}", flush=True)
RES = {}
for s in (1, -1):
    ok = full & (SD == s) & ~np.isnan(lab)
    ms = [lgb.LGBMRegressor(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1,
                            colsample_bytree=0.5, reg_lambda=10.0, verbose=-1, n_jobs=4, random_state=seed).fit(X[ok], lab[ok].clip(-1.5, 4.0)) for seed in range(3)]
    w = np.flatnonzero(last & (SD == s))
    a = np.mean([m.predict(X[w]) for m in ms], axis=0)
    b = TV.model_score(M["models"][str(s)], X[w].astype(float))
    ta, tb = np.quantile(a, 0.99), float(M["thr"][str(s)])
    sa, sb = a >= ta, b >= tb
    print(f"сторона {s:+d}: событий {len(w)}, обучающих {ok.sum()}, корреляция оценок {np.corrcoef(a, b)[0, 1]:.4f}; выше порога: пересборка {sa.sum()}, бот {sb.sum()}, общих {(sa & sb).sum()}", flush=True)
    RES[str(s)] = {"corr": float(np.corrcoef(a, b)[0, 1]), "rebuilt": int(sa.sum()), "bot": int(sb.sum()), "both": int((sa & sb).sum()), "events": int(len(w))}
json.dump(RES, open(f"{ST}/prv_repro.json", "w"), indent=1)   # for the monthly retrain's decision (prv_decide.py)
print("prv repro done", flush=True)
