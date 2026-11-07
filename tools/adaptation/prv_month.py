"""P/R's monthly retrain (RETRAIN.md: the last 24 months to the end of last month), on prv_ev2.py's events (PRV_OUT/prv_ev, the
127 research coins) — prv_export3.py's export recipe (the label stop 1.5 ATR / take 3R clipped to [-1.5, 4], 3 LightGBM per side,
seeds 0..2, a 10-day gap; the threshold = q 0.99 of the last 12 months' scores of the side): only the trees, the thresholds,
"trained_to" and "train.from" of the deployed vp_prv_model.json change (its rules of v0.99.639–670 kept). The check: the old and
the new model on the last month's events (the 1h chart, the BTC filters): how many over each one's threshold.
-> <OUT>/vp_prv_model.json (the repo's file untouched). usage: PRV_OUT=… prv_month.py"""
import os, sys, re, json, datetime as dt, numpy as np, lightgbm as lgb
HERE = os.path.dirname(os.path.abspath(__file__))
for p in ("../neuro_model", "../prv_audit", "../winrate"): sys.path.insert(0, os.path.join(HERE, p))
import nx_feat, treevec as TV
from lgbpure import export
from prv_ev import STOPS, TAKES, BAND_NAMES
OUT = os.environ.get("PRV_OUT", "/home/user/prv_month"); NAMES = BAND_NAMES + nx_feat.NAMES
REPO = os.path.join(HERE, "..", "..")
M = json.load(open(f"{REPO}/vp_prv_model.json")); assert M["feats"] == NAMES
src = open(f"{REPO}/vp_poc_screener.py").read()
C127 = re.search(r'RESEARCH_COINS_127 = tuple\("""(.*?)"""', src, re.S).group(1).split()
syms = sorted({x for c in C127 for x in (c.replace("_USDT", "") + "USDT", "1000" + c.replace("_USDT", "") + "USDT") if os.path.exists(f"{OUT}/prv_ev/{x}.npz")})
Xs, Ys, Ts = [], [], []
for s in syms:
    z = np.load(f"{OUT}/prv_ev/{s}.npz")
    if len(z["t"]): Xs.append(z["X"]); Ys.append(z["Y"]); Ts.append(z["t"])
X = np.concatenate(Xs); Y = np.concatenate(Ys); T = np.concatenate(Ts)
Y = np.where(np.abs(Y) > 20, np.nan, Y); lab = Y[:, STOPS.index(1.5), TAKES.index(3.0)]
F = {n: X[:, i] for i, n in enumerate(NAMES)}; SD = F["side"].astype(int); TF = F["tf"].astype(int)
def month_add(t, k):
    d = dt.datetime.fromtimestamp(int(t), dt.timezone.utc); m = d.month - 1 + k
    return int(dt.datetime(d.year + m // 12, m % 12 + 1, 1, tzinfo=dt.timezone.utc).timestamp())
D_ = lambda t: dt.datetime.fromtimestamp(int(t), dt.timezone.utc).strftime("%Y-%m-%d")
GAP, WIN, Q = 10 * 86400, 24, float(M.get("q") or 0.99)
tmax = int(T.max()); told = int(M["trained_to"])
full = (T < tmax - GAP) & (T >= month_add(tmax, -WIN) - GAP); last = T >= tmax - 365 * 86400
print(f"монет {len(syms)}, событий {len(T)}, данные по {D_(tmax)}; было обучено по {D_(told)}", flush=True)
assert tmax > told + 20 * 86400, "no new month of data"
BTCF, BTCF1, TFS = float(M.get("btc_filter") or 4.0), float(M.get("btc_filter_1h") or 1.0), set(M.get("tfs") or [1])
mo = (T > told) & (T <= tmax)   # the new month: the old model's out of sample
ok_f = (SD * F["b_r24"] > -BTCF) & (SD * F["b_r1"] > -BTCF1) & np.isin(TF, list(TFS))
models, thr, cmp = {}, {}, {}
for s in (1, -1):
    ok = full & (SD == s) & ~np.isnan(lab)
    ms = [lgb.LGBMRegressor(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1,
                            colsample_bytree=0.5, reg_lambda=10.0, verbose=-1, n_jobs=4, random_state=seed).fit(X[ok], lab[ok].clip(-1.5, 4.0)) for seed in range(3)]
    models[str(s)] = [export(m.booster_, NAMES)["trees"] for m in ms]
    w = np.flatnonzero(last & (SD == s)); thr[str(s)] = round(float(np.quantile(np.mean([m.predict(X[w]) for m in ms], axis=0), Q)), 6)
    v = np.flatnonzero(mo & (SD == s) & ok_f)
    a = np.mean([m.predict(X[v]) for m in ms], axis=0) if len(v) else np.array([])
    b = TV.model_score(M["models"][str(s)], X[v].astype(float)) if len(v) else np.array([])
    w12 = np.flatnonzero(last & (SD == s) & ok_f); a12 = np.mean([m.predict(X[w12]) for m in ms], axis=0) if len(w12) else np.array([])
    cmp[str(s)] = {"events": int(len(v)), "new": int((a >= thr[str(s)]).sum()), "old": int((b >= float(M["thr"][str(s)])).sum()),
                   "new_month_avg": round(float((a12 >= thr[str(s)]).sum()) / 12.0, 2),   # the new model's own monthly average (the last 12 months)
                   "both": int(((a >= thr[str(s)]) & (b >= float(M["thr"][str(s)]))).sum()), "train": int(ok.sum()),
                   "thr_old": float(M["thr"][str(s)]), "thr_new": thr[str(s)]}
    print(f"сторона {s:+d}: обучающих {ok.sum()}, порог {M['thr'][str(s)]} -> {thr[str(s)]}; в новом месяце событий {len(v)}, "
          f"выше порога: старая {cmp[str(s)]['old']}, новая {cmp[str(s)]['new']}, общих {cmp[str(s)]['both']}", flush=True)
N = dict(M); N["models"] = models; N["thr"] = thr; N["trained_to"] = tmax
N["train"] = dict(M.get("train") or {}, window_months=WIN, **{"from": int(month_add(tmax, -WIN))})
json.dump(N, open(f"{OUT}/vp_prv_model.json", "w"), separators=(",", ":"))
json.dump({"cmp": cmp, "trained_to": tmax, "old_trained_to": told}, open(f"{OUT}/prv_month_cmp.json", "w"), indent=1)
print("KB", os.path.getsize(f"{OUT}/vp_prv_model.json") // 1024, "prv month done", flush=True)
