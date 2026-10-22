"""⚡ 15m deep limits (v0.99.679) export: the 2026 walk-forward model of deep2 / exit E0 (trained on the 85 train coins'
fills closed before 2026, the same random sample and seed as the walk-forward run), the threshold = q 0.98 of its 2025
out-of-sample scores (the walk-forward rule); the backtest list = the walk-forward trades (q 0.98, cap 12) of all 127
coins from 2025 on, re-simulated for the fill / exit prices."""
import json, os, numpy as np, lightgbm as lgb, warnings
warnings.filterwarnings("ignore")
import s15_engine as E
from s15_wf import load, select
from mk import ts
from lgbpure import export
from bt_trades import gate_sym
D = load("s15", [0])
T, F, TR = D["t"], D["F"], ~D["chk"]
y = np.clip(D["R"][0], -1.5, 1.5)
rng = np.random.default_rng(0)
pr = dict(n_estimators=300, learning_rate=0.05, num_leaves=63, min_child_samples=1000, subsample=0.7, subsample_freq=1,
          colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
model = None
for Y in (2022, 2023, 2024, 2025, 2026):   # replay the walk-forward loop: the same rng draws, the 2026 model kept
    tr = np.flatnonzero(TR & (T < ts(Y) - 3 * 86400))
    if len(tr) < 20000: continue
    if len(tr) > 1500000: tr = rng.choice(tr, 1500000, replace=False)
    if Y == 2026:
        model = lgb.LGBMRegressor(random_state=0, **pr).fit(F[tr], y[tr])
z = np.load("s15_sc_deep2_0.npz", allow_pickle=True); SC, THR = z["SC"], z["THR"].item()
thr = float(np.quantile(THR[2026], 0.98))
te = T >= ts(2026)
sc26 = model.predict(F[te])
print("model == walk-forward 2026 scores:", float(np.max(np.abs(sc26 - SC[te]))), "thr", round(thr, 6))
trees = export(model.booster_, E.FNAMES)["trees"]
# ---- backtest list ----
out = []
TK, ST, HD = E.EXITS[0]
for setname, sub in (("train", TR), ("check", D["chk"])):
    sel = select(D, 0, SC, THR, 0.98, 12, sub)
    sel = sel[T[sel] >= ts(2025)]
    by = {}
    for i in sel: by.setdefault(D["names"][D["sym"][i]], []).append(i)
    for sym, idx in by.items():
        Tb, O, H, L, C, V = E.load15(sym); atr = E.wilder(H, L, C, 14)
        zz = np.load(f"s15/{sym}.npz"); pos = {(int(t), int(s)): k for k, (t, s, f) in enumerate(zip(zz["t"], zz["side"], zz["fam"])) if f == 0}
        gs, scl = gate_sym(sym)
        for i in idx:
            s = int(D["side"][i]); k = pos[(int(T[i]), s)]; bi = int(zz["i"][k]); a = float(atr[bi])
            lv = C[bi] - s * 2.0 * a
            fb = next(b for b in range(bi + 1, bi + 5) if ((L[b] <= lv) if s > 0 else (H[b] >= lv)))
            fill = min(lv, O[fb]) if s > 0 else max(lv, O[fb])
            risk = ST * a; sl = fill - s * risk; tp = fill + s * TK * a
            e_ = min(len(C), fb + HD); kk = e_ - 1 - fb; ex = C[e_ - 1]; kind = "time"
            for q in range(e_ - fb):
                b = fb + q
                if (L[b] <= sl) if s > 0 else (H[b] >= sl):
                    ex = O[b] if (q > 0 and ((O[b] <= sl) if s > 0 else (O[b] >= sl))) else sl; kk = q; kind = "stop"; break
                if q > 0 and ((H[b] >= tp) if s > 0 else (L[b] <= tp)):
                    ex = tp; kk = q; kind = "take"; break
            fee = (0.0002 + (0.0002 if kind == "take" else 0.0005) + 0.0003 * (kk + 1) / 96) * fill
            r = (s * (ex - fill) - fee) / risk
            if abs(r - float(D["R"][0][i])) > 1e-3: print("mismatch", sym, r, D["R"][0][i])
            out.append({"s": gs, "d": s, "c": "15m", "t": int(Tb[bi + 1]), "lv": round(lv / scl, 10), "e": round(fill / scl, 10),
                        "sl": round(sl / scl, 10), "tp": round(tp / scl, 10), "f": int(Tb[fb]), "x": int(Tb[fb + kk] + 900),
                        "xp": round(float(ex) / scl, 10), "r": round(float(r), 3), "k": kind, "chk": setname == "check"})
out.sort(key=lambda x: x["t"])
json.dump(out, open("dlm_bt_v679.json", "w"), separators=(",", ":"))
rr = np.array([x["r"] for x in out]); tt = np.array([x["t"] for x in out]); kd = np.array([x["k"] for x in out])
print("backtest list", len(out), "avg", round(rr.mean(), 3), "wr", round((kd == "take").mean() * 100, 1))
# research numbers (the whole 2022-26 walk-forward, s15_wf / s15_real / s15_money)
years = {}
for setname, sub in (("train", TR), ("check", D["chk"])):
    sel = select(D, 0, SC, THR, 0.98, 12, sub); sel = sel[T[sel] >= ts(2022)]
    for Y in range(2022, 2027):
        m = (T[sel] >= ts(Y)) & (T[sel] < ts(Y + 1))
        rs = D["R"][0][sel][m]; ws = D["W"][0][sel][m]
        mo = ((ts(Y + 1) if Y < 2026 else ts(2026, 10)) - ts(Y)) / (30.4 * 86400)
        years.setdefault(setname, {})[str(Y)] = {"n": int(m.sum()), "avg": round(float(rs.mean()), 3), "wr": round(float(ws.mean() * 100), 1),
                                                  "pm": round(float(m.sum() / mo), 1), "sum": round(float(rs.sum()), 1)}
print(json.dumps(years))
M = {"ver": 1, "kind": "dlm", "feats": E.FNAMES, "models": [trees], "thr": round(thr, 6), "q": 0.98, "side_cap": 12, "trained_to": int(ts(2026) - 3 * 86400),
     "rule": {"depth_atr": 2.0, "alive_bars": 4, "take_atr": TK, "stop_atr": ST, "hold_bars": HD, "bar_sec": 900},
     "research": {"coins": 127, "train_coins": int(len(set(D["sym"][TR]))), "check_coins": int(len(set(D["sym"][D["chk"]]))), "years": years,
                  "m1": {"wr": 85, "avg_through": 0.05, "avg_taker": 0.018, "avg_touch": 0.075},
                  "money": {"train_x": 2.97, "check_x": 1.38, "risk": 1.0}}}
json.dump(M, open("vp_dlm_model_v1.json", "w"), separators=(",", ":"))
print("model size", os.path.getsize("vp_dlm_model_v1.json"))
