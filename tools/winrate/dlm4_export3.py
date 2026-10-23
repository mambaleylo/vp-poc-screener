"""⚡ v3 (v0.99.689) export — two 4h limit streams in one model file: "wick" (1 ATR beyond the bar's low / high, s23 w1)
and "close" (1.5 ATR from the bar's close, s20h4 d15); each a 20-model ensemble (10 seeds on the 28 engine features + 10
with the 5 daily ones), the 2026 walk-forward models (the 85 train coins' fills closed before 2026, label = R of take 1
/ stop 2 ATR / 32 bars), the threshold = q 0.99 of the mean's 2025 out-of-sample train scores (s26_mix.py). The
backtest list = the pooled walk-forward trades from 2025 on (both streams' top 1%, one position per coin & side across
the streams, at most 20 a side; both streams' orders stand, the first to fill is the trade — as the bot does),
re-simulated for the fill / exit prices."""
import os; os.environ["TFH"] = "4"
import json, glob, numpy as np, lightgbm as lgb, warnings
warnings.filterwarnings("ignore")
import s20h4_engine as E20, s23_engine as E23
from s15_wf import load, select
from mk import ts
from lgbpure import export
from bt_trades import gate_sym
Q, CAP = 0.99, 20
TK, ST, HD = 1.0, 2.0, 32
FN = list(E23.FNAMES) + ["d_e20", "d_e50", "d_rsi", "d_pos20", "b_d_e50"]
assert list(E20.FNAMES) == list(E23.FNAMES)
def merged(dr, fi):
    a = load(dr, [fi]); b = load(dr + "x", [fi]); n0 = len(a["names"]); X = {}
    for k in a:
        if k == "names": continue
        ax = 1 if k in ("R", "K", "W") else 0
        X[k] = np.concatenate([a[k], (b[k] + n0 if k == "sym" else (np.zeros_like(b[k]) if k == "chk" else b[k]))], axis=ax)
    X["names"] = a["names"] + b["names"]; X["new"] = np.r_[np.zeros(len(a["t"]), bool), np.ones(len(b["t"]), bool)]
    X["usdc"] = np.array([X["names"][k] == "USDCUSDT" for k in X["sym"]]); X["n0"] = len(a["t"])
    F2 = []
    for d in (dr, dr + "x"):
        for f in sorted(glob.glob(f"{d}/*.npz")):
            z = np.load(f); m = z["fam"] == fi
            if m.any(): F2.append(np.load(f"f2_{d}/{os.path.basename(f)}")["F2"][m])
    X["F33"] = np.concatenate([X["F"], np.concatenate(F2)[:, [0, 1, 2, 5, 8]]], axis=1)
    return X
STREAMS = [("wick", "s23_4h", 2, 0, "s26_s23_4h_w1_0.npz", E23, {"anchor": "wick", "depth_atr": 1.0, "fam": 2.0}),
           ("close", "s20h4", 1, 1, "s26_s20h4_d15_1.npz", E20, {"anchor": "close", "depth_atr": 1.5, "fam": 1.0})]
pr = dict(n_estimators=300, learning_rate=0.05, num_leaves=63, min_child_samples=1000, subsample=0.7, subsample_freq=1,
          colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
out_streams, EV, DS = [], [], {}
for name, dr, fi, ex, scf, E, st in STREAMS:
    X = merged(dr, fi); DS[name] = (X, dr, fi, ex, E, st)
    T = X["t"]; TR = ~X["chk"] & ~X["new"]; y = np.clip(X["R"][ex], -1.5, 1.5)
    tr = np.flatnonzero(TR & (T < ts(2026) - 3 * 86400)); assert len(tr) <= 800000
    te = T >= ts(2026); models, pred = [], np.zeros(int(te.sum()))
    for F in (X["F"], X["F33"]):
        for seed in range(10):
            m = lgb.LGBMRegressor(random_state=seed, **pr).fit(F[tr], y[tr])
            pred += m.predict(F[te]) / 20
            models.append(export(m.booster_, FN[:F.shape[1]])["trees"])
    z = np.load(scf, allow_pickle=True); SC, THR = z["SC"], z["THR"].item()
    print(name, "model == walk-forward 2026 scores:", float(np.max(np.abs(pred - SC[te]))), flush=True)
    thr = float(np.quantile(THR[2026], Q))
    out_streams.append(dict(st, name=name, models=models, thr=round(thr, 6)))
    yr = T.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970
    thr_r = np.full(len(T), np.inf)
    for Y, v in THR.items(): thr_r[yr == Y] = np.quantile(v, Q)
    for i in np.flatnonzero(~X["usdc"] & np.isfinite(SC) & (SC >= thr_r) & (T >= ts(2022))):   # every event above its stream's threshold (as the bot sees them)
        EV.append((int(T[i]), -float(SC[i]), name, int(i)))
# ---- the pool: one position per coin & side across the streams, 20 a side; the bot places both streams' orders, the
# first to fill is the trade -> the pool by (the signal's bar, the fill bar, the higher score) ----
_BC = {}
def fill_time(name, i):
    X, dr, fi, ex, E, st = DS[name]; sym = X["names"][X["sym"][i]]; s = int(X["side"][i]); t = int(X["t"][i])
    if sym not in _BC:
        Tb, O, H, L, C, V = E.load15(sym); _BC[sym] = (Tb, O, H, L, C, E.wilder(H, L, C, 14), {int(x): j for j, x in enumerate(Tb)})
    Tb, O, H, L, C, atr, pos = _BC[sym]; bi = pos[t]; a = float(atr[bi])
    lv = ((L[bi] if s > 0 else H[bi]) if st["anchor"] == "wick" else C[bi]) - s * st["depth_atr"] * a
    return int(Tb[next(b for b in range(bi + 1, bi + 5) if ((L[b] <= lv) if s > 0 else (H[b] >= lv)))])
EV = sorted((t, fill_time(name, i), nsc, name, i) for t, nsc, name, i in EV)
EV = [(t, nsc, name, i) for t, ft, nsc, name, i in EV]
busy, act, pool = {}, [], []
for t, nsc, name, i in EV:
    X, dr, fi, ex, E, st = DS[name]; sym = X["names"][X["sym"][i]]; s = int(X["side"][i])
    if busy.get((sym, s), 0) > t: continue
    act = [a for a in act if a[0] > t]
    if sum(1 for a in act if a[1] == s) >= CAP: continue
    end = t + int(X["K"][ex][i]) * 3600; busy[(sym, s)] = end; act.append((end, s)); pool.append((name, i))
years, out = {}, []
for name, i in pool:
    X, dr, fi, ex, E, st = DS[name]; t = int(X["t"][i])
    part = "train" if not (X["chk"][i] or X["new"][i]) else ("check" if X["chk"][i] else "new")
    Y = str(int(np.datetime64(t, "s").astype("datetime64[Y]").astype(int) + 1970))
    d = years.setdefault(part, {}).setdefault(Y, {"n": 0, "sum": 0.0, "w": 0})
    d["n"] += 1; d["sum"] += float(X["R"][ex][i]); d["w"] += int(X["W"][ex][i])
    if t < ts(2025): continue
    sym = X["names"][X["sym"][i]]; s = int(X["side"][i])
    dd_ = dr + "x" if i >= X["n0"] else dr
    Tb, O, H, L, C, V = E.load15(sym); atr = E.wilder(H, L, C, 14)
    zz = np.load(f"{dd_}/{sym}.npz"); k = np.flatnonzero((zz["t"] == t) & (zz["side"] == s) & (zz["fam"] == fi))[0]
    bi = int(zz["i"][k]); a = float(atr[bi])
    lv = ((L[bi] if s > 0 else H[bi]) if st["anchor"] == "wick" else C[bi]) - s * st["depth_atr"] * a
    fb = next(b for b in range(bi + 1, bi + 5) if ((L[b] <= lv) if s > 0 else (H[b] >= lv)))
    fill = min(lv, O[fb]) if s > 0 else max(lv, O[fb])
    risk = ST * a; sl = fill - s * risk; tp = fill + s * TK * a
    e_ = min(len(C), fb + HD); kk = e_ - 1 - fb; exv = C[e_ - 1]; kind = "time"
    for q in range(e_ - fb):
        b = fb + q
        if (L[b] <= sl) if s > 0 else (H[b] >= sl):
            exv = O[b] if (q > 0 and ((O[b] <= sl) if s > 0 else (O[b] >= sl))) else sl; kk = q; kind = "stop"; break
        if q > 0 and ((H[b] >= tp) if s > 0 else (L[b] <= tp)):
            exv = tp; kk = q; kind = "take"; break
    fee = (0.0002 + (0.0002 if kind == "take" else 0.0005) + 0.0003 * (kk + 1) / 6) * fill
    r = (s * (exv - fill) - fee) / risk
    if abs(r - float(X["R"][ex][i])) > 1e-3: print("mismatch", name, sym, r, X["R"][ex][i])
    gs, scl = gate_sym(sym)
    out.append({"s": gs, "d": s, "c": "4h", "st": name, "t": int(Tb[bi + 1]), "lv": round(lv / scl, 10), "e": round(fill / scl, 10),
                "sl": round(sl / scl, 10), "tp": round(tp / scl, 10), "f": int(Tb[fb]), "x": int(Tb[fb + kk] + 14400),
                "xp": round(float(exv) / scl, 10), "r": round(float(r), 3), "k": kind, "chk": part != "train"})
for part in years:
    for Y, d in years[part].items():
        mo = ((ts(int(Y) + 1) if int(Y) < 2026 else ts(2026, 10)) - ts(int(Y))) / (30.4 * 86400)
        years[part][Y] = {"n": d["n"], "avg": round(d["sum"] / d["n"], 3), "wr": round(d["w"] / d["n"] * 100, 1), "pm": round(d["n"] / mo, 1)}
out.sort(key=lambda x: x["t"])
json.dump(out, open("dlm_bt_v689.json", "w"), separators=(",", ":"))
PE = [(int(DS[n][0]["t"][i]), int(DS[n][0]["t"][i]) + int(DS[n][0]["K"][DS[n][3]][i]) * 3600, float(DS[n][0]["R"][DS[n][3]][i]), float(np.clip(2 * DS[n][0]["F"][i, 2] / 100, 0.002, 0.5))) for n, i in pool]
np.save("pool689.npy", np.array(PE))   # the pool order (time, then the higher score) — never by the exit time
rr = np.array([x["r"] for x in out]); kd = np.array([x["k"] for x in out])
print("backtest list", len(out), "avg", round(rr.mean(), 3), "wr", round((kd == "take").mean() * 100, 1), {n: sum(1 for x in out if x["st"] == n) for n in ("wick", "close")})
un_r = [X_r for name, i in pool for X_r in [DS[name][0]["R"][DS[name][3]][i]] if (DS[name][0]["chk"][i] or DS[name][0]["new"][i])]
un_w = [DS[name][0]["W"][DS[name][3]][i] for name, i in pool if (DS[name][0]["chk"][i] or DS[name][0]["new"][i])]
un_t = np.array([DS[name][0]["t"][i] for name, i in pool if (DS[name][0]["chk"][i] or DS[name][0]["new"][i])])
un_r = np.array(un_r); un_w = np.array(un_w); h = un_t >= ts(2025, 10)
M = {"ver": 3, "kind": "dlm", "feats": FN, "streams": out_streams, "q": Q, "side_cap": CAP, "trained_to": int(ts(2026) - 3 * 86400),
     "rule": {"alive_bars": 4, "take_atr": TK, "stop_atr": ST, "hold_bars": HD, "bar_sec": 14400, "tf": "4h", "min_bars": 2000, "depth_min": 0.3, "depth_max": 6.0},
     "research": {"coins": 210, "train_coins": 85, "check_coins": 42, "new_coins": 82, "models_n": 20, "years": years,
                  "unseen": {"wr": round(float(un_w.mean() * 100)), "avg": round(float(un_r.mean()), 3), "last12_wr": round(float(un_w[h].mean() * 100)), "last12_avg": round(float(un_r[h].mean()), 3)},
                  "m1": {"wr": 85, "avg_through": 0.28},
                  "money": {"pos": 20, "risk": 5.0, "year_median": 2789, "year_p10": 819, "harsh_median": 2110, "dd": 51, "m6_below": 0}}}
json.dump(M, open("vp_dlm_model_v3.json", "w"), separators=(",", ":"))
print("model size", os.path.getsize("vp_dlm_model_v3.json"), json.dumps(M["research"]["unseen"]), json.dumps(years))
