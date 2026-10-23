"""⚡ v2 (v0.99.687) export — the 4h "wick" limits: the 2026 walk-forward model of s20h4 wick1 / exit E1 (take 1 / stop 2
ATR / 32 bars; trained on the 85 train coins' fills closed before 2026, the same random sample and seed as the
walk-forward run), the threshold = q 0.99 of its 2025 out-of-sample scores (the walk-forward rule); the backtest list =
the walk-forward trades (q 0.99, cap 12 a side) of the 127 coins and the 83 extra ones (the yearly models applied
unchanged; USDC dropped) from 2025 on, re-simulated for the fill / exit prices."""
import json, os, numpy as np, lightgbm as lgb, warnings
warnings.filterwarnings("ignore")
import s20h4_engine as E
from s15_wf import load, select
from mk import ts
from lgbpure import export
from bt_trades import gate_sym
FAM = E.FAMS.index("wick1"); EX = 1; Q = 0.99
TK, ST, HD = E.EXITS[EX]
D = load("s20h4", [FAM])
T, F, TR = D["t"], D["F"], ~D["chk"]
y = np.clip(D["R"][EX], -1.5, 1.5)
rng = np.random.default_rng(0)
pr = dict(n_estimators=300, learning_rate=0.05, num_leaves=63, min_child_samples=1000, subsample=0.7, subsample_freq=1,
          colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=2)
model = None
for Y in (2022, 2023, 2024, 2025, 2026):   # replay the walk-forward loop (s20h4_wf.py): the same rng draws, the 2026 model kept
    tr = np.flatnonzero(TR & (T < ts(Y) - 3 * 86400))
    if len(tr) < 20000: continue
    if len(tr) > 800000: tr = rng.choice(tr, 800000, replace=False)
    if Y == 2026:
        model = lgb.LGBMRegressor(random_state=0, **pr).fit(F[tr], y[tr])
z = np.load("s20h4_sc_wick1_1.npz", allow_pickle=True); SC, THR = z["SC"], z["THR"].item()
thr = float(np.quantile(THR[2026], Q))
te = T >= ts(2026)
print("model == walk-forward 2026 scores:", float(np.max(np.abs(model.predict(F[te]) - SC[te]))), "thr", round(thr, 6))
trees = export(model.booster_, E.FNAMES)["trees"]
X = load("s20h4x", [FAM]); SCX = np.load("s20h4x_sc_wick1_1.npy")
okx = np.array([X["names"][k] != "USDCUSDT" for k in X["sym"]])
# ---- the backtest list (2025 on) and the per-year research numbers (2022 on) ----
out, years = [], {}
for DD, SS, sets in ((D, SC, (("train", TR), ("check", D["chk"]))), (X, SCX, (("new", okx),))):
    for setname, sub in sets:
        sel = select(DD, EX, SS, THR, Q, 12, sub); sel = sel[DD["t"][sel] >= ts(2022)]
        tt = DD["t"][sel]
        for Y in range(2022, 2027):
            m = (tt >= ts(Y)) & (tt < ts(Y + 1))
            rs = DD["R"][EX][sel][m]; ws = DD["W"][EX][sel][m]
            mo = ((ts(Y + 1) if Y < 2026 else ts(2026, 10)) - ts(Y)) / (30.4 * 86400)
            years.setdefault(setname, {})[str(Y)] = {"n": int(m.sum()), "avg": round(float(rs.mean()), 3) if m.any() else None,
                                                      "wr": round(float(ws.mean() * 100), 1) if m.any() else None, "pm": round(float(m.sum() / mo), 1)}
        dr = "s20h4" if DD is D else "s20h4x"
        by = {}
        for i in sel[DD["t"][sel] >= ts(2025)]: by.setdefault(DD["names"][DD["sym"][i]], []).append(i)
        for sym, idx in by.items():
            Tb, O, H, L, C, V = E.load15(sym); atr = E.wilder(H, L, C, 14)
            zz = np.load(f"{dr}/{sym}.npz"); pos = {(int(t), int(s)): k for k, (t, s, f) in enumerate(zip(zz["t"], zz["side"], zz["fam"])) if f == FAM}
            gs, scl = gate_sym(sym)
            for i in idx:
                s = int(DD["side"][i]); k = pos[(int(DD["t"][i]), s)]; bi = int(zz["i"][k]); a = float(atr[bi])
                lv = (L[bi] if s > 0 else H[bi]) - s * a
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
                fee = (0.0002 + (0.0002 if kind == "take" else 0.0005) + 0.0003 * (kk + 1) / 6) * fill
                r = (s * (ex - fill) - fee) / risk
                if abs(r - float(DD["R"][EX][i])) > 1e-3: print("mismatch", sym, r, DD["R"][EX][i])
                out.append({"s": gs, "d": s, "c": "4h", "t": int(Tb[bi + 1]), "lv": round(lv / scl, 10), "e": round(fill / scl, 10),
                            "sl": round(sl / scl, 10), "tp": round(tp / scl, 10), "f": int(Tb[fb]), "x": int(Tb[fb + kk] + 14400),
                            "xp": round(float(ex) / scl, 10), "r": round(float(r), 3), "k": kind, "chk": setname != "train"})
out.sort(key=lambda x: x["t"])
json.dump(out, open("dlm_bt_v687.json", "w"), separators=(",", ":"))
rr = np.array([x["r"] for x in out]); kd = np.array([x["k"] for x in out])
print("backtest list", len(out), "avg", round(rr.mean(), 3), "wr", round((kd == "take").mean() * 100, 1))
print(json.dumps(years))
M = {"ver": 2, "kind": "dlm", "feats": E.FNAMES, "models": [trees], "thr": round(thr, 6), "q": Q, "side_cap": 12, "trained_to": int(ts(2026) - 3 * 86400),
     "rule": {"family": "wick1", "depth_atr": 1.0, "alive_bars": 4, "take_atr": TK, "stop_atr": ST, "hold_bars": HD, "bar_sec": 14400, "tf": "4h",
              "min_bars": 2000, "depth_min": 0.3, "depth_max": 6.0},
     "research": {"coins": 210, "train_coins": int(len(set(D["sym"][TR]))), "check_coins": int(len(set(D["sym"][D["chk"]]))), "new_coins": int(len(set(X["sym"][okx]))),
                  "years": years,
                  "unseen": {"wr": 78, "avg": 0.168, "last12_wr": 77, "last12_avg": 0.154},
                  "m1": {"wr": 80, "avg_through": 0.21},
                  "money": {"pos": 20, "risk": 3.0, "year_median": 843, "year_p10": 428, "last12": 1634, "m6_median": 245, "m6_below": 2}}}
json.dump(M, open("vp_dlm_model_v2.json", "w"), separators=(",", ":"))
print("model size", os.path.getsize("vp_dlm_model_v2.json"))
