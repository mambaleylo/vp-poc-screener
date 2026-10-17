"""Neuro v3: the chosen rule — yearly check at a few thresholds (saved scores), then the final models on all data"""
import os, sys, json, glob
RULE = tuple(float(x) for x in os.environ.get("RULE", "1.0_2.0_12").split("_"))
Q = float(os.environ.get("Q", 0.995))
import numpy as np, lightgbm as lgb
from mk import ts
from common import D
from lgbpure import export
import nx_feat
from nx_build import STOPS, TAKES, HOLDS
if os.environ.get("Y3"):
    TAKES, HOLDS = (3.0, 4.0, 6.0), (12, 48, 120)
Xs, Ys, Ts, Ss = [], [], [], []
for k, fn in enumerate(sorted(glob.glob(f"{D}/nx/*.npz"))):
    z = np.load(fn)
    if len(z["t"]):
        Xs.append(z["X"]); Ys.append(np.load(fn.replace("/nx/", "/nx3/"))["Y"] if os.environ.get("Y3") else z["Y"]); Ts.append(z["t"]); Ss.append(np.full(len(z["t"]), k, dtype=np.int16))
X = np.concatenate(Xs); Y = np.concatenate(Ys); T = np.concatenate(Ts); SY = np.concatenate(Ss)
del Xs, Ys
ok = X[:, nx_feat.NAMES.index("atr_pct")] >= 0.1
X, Y, T, SY = X[ok], Y[ok], T[ok], SY[ok]
Y = np.where(np.abs(Y) > 20, np.nan, Y)
a_i, t_i, h_i = STOPS.index(RULE[0]), TAKES.index(RULE[1]), HOLDS.index(int(RULE[2]))
lab = {s: Y[:, si, a_i, t_i, h_i] for si, s in enumerate((1, -1))}
def mdl(seed):
    return lgb.LGBMRegressor(n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=2000, subsample=0.5, subsample_freq=1,
                             colsample_bytree=0.5, reg_lambda=10.0, verbose=-1, n_jobs=4, random_state=seed)
fn_sc = f"{D}/nx_sc_{'_'.join(str(x) for x in RULE)}.npz"
if not os.path.exists(fn_sc):
    S = {}
    for Yr in (2022, 2023, 2024, 2025):
        tr = T < ts(Yr) - 3 * 86400
        for s in (1, -1):
            okk = tr & ~np.isnan(lab[s])
            y = lab[s].clip(-1.5, RULE[1] + 1.0)
            S[f"{Yr}_{s}"] = mdl(1).fit(X[okk], y[okk]).predict(X).astype(np.float32)
        print("fold", Yr, flush=True)
    np.savez(fn_sc, **S)
S = np.load(fn_sc)
from nxkit import replay, summ
years = {}
for q in (0.995, 0.997, 0.998):
    line = []
    for Yr in (2022, 2023, 2024, 2025):
        te = (T >= ts(Yr)) & (T < (ts(Yr + 1) if Yr < 2025 else ts(2027)))
        ref = (T >= ts(Yr - 1)) & (T < ts(Yr) - 3 * 86400)
        wk = ((ts(Yr + 1) if Yr < 2025 else ts(2026, 10)) - ts(Yr)) / (7 * 86400)
        t_, sy_, sd_, r_ = [], [], [], []
        for s in (1, -1):
            sc = S[f"{Yr}_{s}"]
            thr = float(np.quantile(sc[ref], q))
            sel = np.where(te & (sc >= thr))[0]
            t_.append(T[sel]); sy_.append(SY[sel]); sd_.append(np.full(len(sel), s)); r_.append(lab[s][sel])
        out = replay(np.concatenate(t_), np.concatenate(sy_), np.concatenate(sd_), np.concatenate(r_), int(RULE[2]))
        st = summ(out, wk)
        line.append(f"{Yr}: {st['avg']:+.2f}R×{st['wk']}/нед WR{st['wr']} Σ{st['sum']:.0f} dd{st['dd']:.0f}")
        if q == Q:
            years[str(Yr)] = st
    print(f"top{(1 - q) * 100:.1f}%: " + " | ".join(line), flush=True)
if os.environ.get("EXPORT") == "1":
    full = T < T.max() - 2 * 86400
    models, thr = {}, {}
    last = T >= T.max() - 365 * 86400
    for s in (1, -1):
        okk = full & ~np.isnan(lab[s])
        y = lab[s].clip(-1.5, RULE[1] + 1.0)
        ms, sc = [], np.zeros(len(T))
        for seed in range(3):
            m = mdl(seed).fit(X[okk], y[okk])
            ms.append(export(m.booster_, nx_feat.NAMES)["trees"])
            sc += m.predict(X) / 3
        models[str(s)] = ms
        thr[str(s)] = round(float(np.quantile(sc[last], Q)), 6)
        print("side", s, "thr", thr[str(s)], flush=True)
    out = {"ver": 1, "kind": "neuro_v3", "feats": nx_feat.NAMES, "models": models, "thr": thr, "q": Q,
           "rule": {"stop_atr": RULE[0], "take_r": RULE[1], "hold_h": int(RULE[2])}, "side_cap": 12, "trained_to": int(T.max()),
           "research": {"coins": 127, "cap": 12, "q": Q, "years": years}}
    json.dump(out, open(f"{D}/vp_neuro_model{os.environ.get('Y3', '')}.json", "w"), separators=(",", ":"))
    print("KB", os.path.getsize(f"{D}/vp_neuro_model{os.environ.get('Y3', '')}.json") // 1024)
