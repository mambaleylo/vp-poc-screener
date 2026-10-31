"""what the ⚡ model looks at: per stream one LightGBM of the deployed recipe (all 33 features, seed 0) trained on the train
coins' orders closed 3 days before 2026; SHAP (pred_contrib) of the 2026 orders of every coin: the mean |SHAP| a feature,
the mean SHAP of the chosen ones (score >= the year's q0.99), its direction (the corr of the value with its SHAP).
-> <LABSTORE>/wf/explain_<stream>.json (+ the 2026 orders' SHAP for the examples, explain_<stream>.npz)"""
import sys, os, json, calendar, numpy as np, lightgbm as lgb, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
ts = lambda y, m=1, d=1: calendar.timegm((y, m, d, 0, 0, 0))
from common import V
NAMES = V.DLM_FNAMES4
C = json.load(open(f"{ST}/feat_coins.json"))
def bn(gs):
    b = gs.replace("_USDT", "")
    for c in (b + "USDT", "1000" + b + "USDT"):
        if c in C["base"] or c in C["new"]: return c
r127 = sorted({bn(c) for c in V.RESEARCH_COINS_127 if bn(c)}); check = set(r127[2::3]); train = set(r127) - check
pr = dict(n_estimators=300, learning_rate=0.05, num_leaves=63, min_child_samples=1000, subsample=0.7, subsample_freq=1,
          colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
Y = 2026
for stream in ("wick4h", "close2h"):
    X, y, T, tout, coin, side, isTr = [], [], [], [], [], [], []
    for c in C["base"]:
        fn = f"{ST}/feat/{stream}/{c}.npz"
        if not os.path.exists(fn): continue
        z = np.load(fn)
        if not len(z["t"]): continue
        X.append(z["F"]); y.append(np.clip(z["R"], -1.5, 1.5)); T.append(z["t"]); tout.append(z["tout"]); coin += [c] * len(z["t"]); side.append(z["side"])
        isTr.append(np.full(len(z["t"]), c in train))
    X = np.concatenate(X); y = np.concatenate(y); T = np.concatenate(T); tout = np.concatenate(tout); side = np.concatenate(side); isTr = np.concatenate(isTr); coin = np.array(coin)
    tr = isTr & (tout < ts(Y) - 3 * 86400)
    m = lgb.LGBMRegressor(random_state=0, **pr).fit(X[tr], y[tr])
    ref = isTr & (T >= ts(Y - 1)) & (T < ts(Y)); thr = float(np.quantile(m.predict(X[ref]), 0.99))
    te = np.flatnonzero((T >= ts(Y)) & (T < ts(Y + 1)))
    sh = m.predict(X[te], pred_contrib=True); sc = sh.sum(1); base = float(sh[0, -1]); sh = sh[:, :-1]
    sel = sc >= thr
    out = {"thr": thr, "base": base, "n": int(len(te)), "n_sel": int(sel.sum()), "feat": []}
    for j, nm in enumerate(NAMES):
        x = X[te, j]; s = sh[:, j]
        ok = np.isfinite(x)
        cor = float(np.corrcoef(x[ok], s[ok])[0, 1]) if ok.sum() > 10 and np.std(x[ok]) > 0 and np.std(s[ok]) > 0 else 0.0
        out["feat"].append({"f": nm, "abs": float(np.mean(np.abs(s))), "sel": float(np.mean(s[sel])), "sel_x": float(np.median(x[sel & ok])) if (sel & ok).any() else None,
                            "all_x": float(np.median(x[ok])), "cor": cor})
    out["feat"].sort(key=lambda d: -d["abs"])
    json.dump(out, open(f"{ST}/wf/explain_{stream}.json", "w"), indent=1)
    np.savez_compressed(f"{ST}/wf/explain_{stream}.npz", coin=coin[te], t=T[te], side=side[te], F=X[te], shap=sh, score=sc, base=base, thr=thr)
    print(stream, "thr", round(thr, 4), "base", round(base, 4), "chosen", int(sel.sum()), "of", len(te), flush=True)
    for d in out["feat"][:14]:
        print(f"   {d['f']:8s} |SHAP| {d['abs']:.4f}  у выбранных {d['sel']:+.4f}  значение выбранных {d['sel_x']:+.2f} / всех {d['all_x']:+.2f}  направление {d['cor']:+.2f}", flush=True)
