"""⚡ v2 (v0.99.687) export — the 4h "wick" limits, the final model: a 20-model ensemble — 10 LightGBM (seeds 0–9) on the
28 engine features and 10 on those + 5 daily context features (the coin's close vs its daily EMA20 / EMA50 in daily
ATRs, its daily RSI14, its place in the 20-day range, BTC's close vs its daily EMA50) — each the 2026 walk-forward
model (trained on the 85 train coins' fills closed before 2026, label = R of take 1 / stop 2 ATR / 32 bars), the score
= the mean of the 20; the threshold = q 0.99 of the mean's 2025 out-of-sample scores of the train coins (s25_ens.py ->
s25_money3.py / s25_mixcheck.py). The backtest list = the walk-forward trades (q 0.99, cap 20 a side) of all 210 coins
from 2025 on, re-simulated for the fill / exit prices."""
import os; os.environ["TFH"] = "4"
import json, glob, numpy as np, lightgbm as lgb, warnings
warnings.filterwarnings("ignore")
import s23_engine as E
from s15_wf import load, select
from mk import ts
from lgbpure import export
from bt_trades import gate_sym
Q, CAP, EX = 0.99, 20, 0
TK, ST, HD = E.EXITS[EX]
X2 = ["d_e20", "d_e50", "d_rsi", "d_pos20", "b_d_e50"]; USE = [0, 1, 2, 5, 8]
FN = list(E.FNAMES) + X2
def merged():
    a = load("s23_4h", [2]); b = load("s23_4hx", [2]); n0 = len(a["names"]); D = {}
    for k in a:
        if k == "names": continue
        ax = 1 if k in ("R", "K", "W") else 0
        D[k] = np.concatenate([a[k], (b[k] + n0 if k == "sym" else (np.zeros_like(b[k]) if k == "chk" else b[k]))], axis=ax)
    D["names"] = a["names"] + b["names"]; D["new"] = np.r_[np.zeros(len(a["t"]), bool), np.ones(len(b["t"]), bool)]
    D["usdc"] = np.array([D["names"][k] == "USDCUSDT" for k in D["sym"]])
    F2 = np.concatenate([np.load(f)["F2"] for d in ("s24_4h", "s24_4hx") for f in sorted(glob.glob(f"{d}/*.npz"))])
    t2 = np.concatenate([np.load(f)["t"] for d in ("s24_4h", "s24_4hx") for f in sorted(glob.glob(f"{d}/*.npz"))])
    assert (t2 == D["t"]).all()
    D["F33"] = np.concatenate([D["F"], F2[:, USE]], axis=1)
    return D
D = merged()
T = D["t"]; TR = ~D["chk"] & ~D["new"]
y = np.clip(D["R"][EX], -1.5, 1.5)
pr = dict(n_estimators=300, learning_rate=0.05, num_leaves=63, min_child_samples=1000, subsample=0.7, subsample_freq=1,
          colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
tr = np.flatnonzero(TR & (T < ts(2026) - 3 * 86400)); assert len(tr) <= 800000
te = T >= ts(2026)
models, pred = [], np.zeros(int(te.sum()))
for X in (D["F"], D["F33"]):
    for seed in range(10):
        m = lgb.LGBMRegressor(random_state=seed, **pr).fit(X[tr], y[tr])
        pred += m.predict(X[te]) / 20
        models.append(export(m.booster_, FN[:X.shape[1]])["trees"])
za = np.load("s25_sc_4h_w1_0_A_base.npz", allow_pickle=True); zb = np.load("s25_sc_4h_w1_0_A_0-1-2-5-8.npz", allow_pickle=True)
ta, tb_ = za["THR"].item(), zb["THR"].item()
SC = (za["SC"] + zb["SC"]) / 2; THR = {Y: (ta[Y] + tb_[Y]) / 2 for Y in ta}
print("model == walk-forward 2026 scores:", float(np.max(np.abs(pred - SC[te]))))
thr = float(np.quantile(THR[2026], Q)); print("thr", thr)
# ---- the backtest list (2025 on), the per-year numbers (2022 on) ----
out, years = [], {}
sets = (("train", TR & ~D["usdc"]), ("check", D["chk"]), ("new", D["new"] & ~D["usdc"]))
sel_all = select(D, EX, SC, THR, Q, CAP, ~D["usdc"]); sel_all = sel_all[T[sel_all] >= ts(2022)]
for setname, sub in sets:
    sel = sel_all[sub[sel_all]]; tt = T[sel]
    for Y in range(2022, 2027):
        mm = (tt >= ts(Y)) & (tt < ts(Y + 1)); rs = D["R"][EX][sel][mm]; ws = D["W"][EX][sel][mm]
        mo = ((ts(Y + 1) if Y < 2026 else ts(2026, 10)) - ts(Y)) / (30.4 * 86400)
        years.setdefault(setname, {})[str(Y)] = {"n": int(mm.sum()), "avg": round(float(rs.mean()), 3) if mm.any() else None,
                                                  "wr": round(float(ws.mean() * 100), 1) if mm.any() else None, "pm": round(float(mm.sum() / mo), 1)}
by = {}
for i in sel_all[T[sel_all] >= ts(2025)]: by.setdefault(D["names"][D["sym"][i]], []).append(i)
n127 = int((~D["new"]).sum())
for sym, idx in by.items():
    dr = "s23_4hx" if idx[0] >= n127 else "s23_4h"
    Tb, O, H, L, C, V = E.load15(sym); atr = E.wilder(H, L, C, 14)
    zz = np.load(f"{dr}/{sym}.npz"); pos = {(int(t), int(s)): k for k, (t, s, f) in enumerate(zip(zz["t"], zz["side"], zz["fam"])) if f == 2}
    gs, scl = gate_sym(sym)
    for i in idx:
        s = int(D["side"][i]); k = pos[(int(T[i]), s)]; bi = int(zz["i"][k]); a = float(atr[bi])
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
        if abs(r - float(D["R"][EX][i])) > 1e-3: print("mismatch", sym, r, D["R"][EX][i])
        out.append({"s": gs, "d": s, "c": "4h", "t": int(Tb[bi + 1]), "lv": round(lv / scl, 10), "e": round(fill / scl, 10),
                    "sl": round(sl / scl, 10), "tp": round(tp / scl, 10), "f": int(Tb[fb]), "x": int(Tb[fb + kk] + 14400),
                    "xp": round(float(ex) / scl, 10), "r": round(float(r), 3), "k": kind, "chk": bool(D["chk"][i] or D["new"][i])})
out.sort(key=lambda x: x["t"])
json.dump(out, open("dlm_bt_v687.json", "w"), separators=(",", ":"))
rr = np.array([x["r"] for x in out]); kd = np.array([x["k"] for x in out])
print("backtest list", len(out), "avg", round(rr.mean(), 3), "wr", round((kd == "take").mean() * 100, 1))
print(json.dumps(years))
un = sel_all[(D["chk"] | D["new"])[sel_all] & ~D["usdc"][sel_all]]; h = un[T[un] >= ts(2025, 10)]
M = {"ver": 2, "kind": "dlm", "feats": FN, "models": models, "thr": round(thr, 6), "q": Q, "side_cap": CAP, "trained_to": int(ts(2026) - 3 * 86400),
     "rule": {"family": "wick1", "depth_atr": 1.0, "alive_bars": 4, "take_atr": TK, "stop_atr": ST, "hold_bars": HD, "bar_sec": 14400, "tf": "4h",
              "min_bars": 2000, "depth_min": 0.3, "depth_max": 6.0},
     "research": {"coins": 210, "train_coins": int(len(set(D["sym"][TR]))), "check_coins": int(len(set(D["sym"][D["chk"]]))),
                  "new_coins": int(len(set(D["sym"][D["new"] & ~D["usdc"]]))), "models_n": 20, "years": years,
                  "unseen": {"wr": round(float(D["W"][EX][un].mean() * 100)), "avg": round(float(D["R"][EX][un].mean()), 3),
                             "last12_wr": round(float(D["W"][EX][h].mean() * 100)), "last12_avg": round(float(D["R"][EX][h].mean()), 3)},
                  "m1": {"wr": 86, "avg_through": 0.31},
                  "money": {"pos": 20, "risk": 3.0, "year_median": 1146, "year_p10": 406, "last12": 3776, "m6_below": 0}}}
json.dump(M, open("vp_dlm_model_v2.json", "w"), separators=(",", ":"))
print("model size", os.path.getsize("vp_dlm_model_v2.json"), json.dumps(M["research"]["unseen"]))
