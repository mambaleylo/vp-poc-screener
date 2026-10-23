"""⚡ v0.99.689 export — two limit streams, each with its own chart, rule and 20-model ensemble (10 seeds on the 28 engine
features + 10 with the 5 daily ones; the 2026 walk-forward models, the threshold = q 0.99 of the mean's 2025
out-of-sample train scores — s26_mix.py):
  "wick4h"   4h bars, a limit 1 ATR beyond the bar's low / high (s23 w1)
  "close2h"  2h bars, a limit 2 ATR from the bar's close (s21h2 d2)
both: alive 4 bars, take 1 / stop 2 ATR, out after 32 bars. The backtest list = the pool as the bot trades it (pool2h.py):
every signal above its threshold places an order, the first of a coin & side to fill is the trade (busy until its
exit), at most 20 a side; trades from 2025 on, re-simulated for the fill / exit prices."""
import os
import json, glob, importlib, numpy as np, lightgbm as lgb, warnings
warnings.filterwarnings("ignore")
from s15_wf import load
from mk import ts
from lgbpure import export
from bt_trades import gate_sym
Q, CAP, TK, ST, HD = 0.99, 20, 1.0, 2.0, 32
STREAMS = [dict(name="wick4h", dr="s23_4h", eng="s23_engine", tfh=4, fi=2, ex=0, scf="s26_s23_4h_w1_0.npz", anchor="wick", depth_atr=1.0),
           dict(name="close2h", dr="s21h2", eng="s21h2_engine", tfh=2, fi=0, ex=1, scf="s26_s21h2_d2_1.npz", anchor="close", depth_atr=2.0)]
pr = dict(n_estimators=300, learning_rate=0.05, num_leaves=63, min_child_samples=1000, subsample=0.7, subsample_freq=1,
          colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
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
out_streams, EV, FN = [], [], None
for S in STREAMS:
    os.environ["TFH"] = str(S["tfh"]); E = importlib.import_module(S["eng"]); S["E"] = E
    FN = list(E.FNAMES) + ["d_e20", "d_e50", "d_rsi", "d_pos20", "b_d_e50"]
    X = merged(S["dr"], S["fi"]); S["X"] = X
    T = X["t"]; TR = ~X["chk"] & ~X["new"]; y = np.clip(X["R"][S["ex"]], -1.5, 1.5)
    tr = np.flatnonzero(TR & (T < ts(2026) - 3 * 86400)); assert len(tr) <= 800000, len(tr)
    te = T >= ts(2026); models, pred = [], np.zeros(int(te.sum()))
    for F in (X["F"], X["F33"]):
        for seed in range(10):
            m = lgb.LGBMRegressor(random_state=seed, **pr).fit(F[tr], y[tr])
            pred += m.predict(F[te]) / 20
            models.append(export(m.booster_, FN[:F.shape[1]])["trees"])
    z = np.load(S["scf"], allow_pickle=True); SC, THR = z["SC"], z["THR"].item()
    print(S["name"], "model == walk-forward 2026 scores:", float(np.max(np.abs(pred - SC[te]))), flush=True)
    out_streams.append({"name": S["name"], "tf": f"{S['tfh']}h", "bar_sec": S["tfh"] * 3600, "anchor": S["anchor"], "depth_atr": S["depth_atr"],
                        "fam": float(S["fi"]), "alive_bars": 4, "take_atr": TK, "stop_atr": ST, "hold_bars": HD, "models": models,
                        "thr": round(float(np.quantile(THR[2026], Q)), 6)})
    yr = T.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970; thr = np.full(len(T), np.inf)
    for Y, v in THR.items(): thr[yr == Y] = np.quantile(v, Q)
    cache = {}
    for i in np.flatnonzero(~X["usdc"] & np.isfinite(SC) & (SC >= thr) & (T >= ts(2022))):
        sym = X["names"][X["sym"][i]]; s = int(X["side"][i]); t = int(T[i])
        if sym not in cache:
            Tb, O, H, L, C, V = E.load15(sym); cache[sym] = (Tb, O, H, L, C, E.wilder(H, L, C, 14), {int(x): j for j, x in enumerate(Tb)})
        Tb, O, H, L, C, atr, pos = cache[sym]; bi = pos[t]; a = float(atr[bi])
        lv = ((L[bi] if s > 0 else H[bi]) if S["anchor"] == "wick" else C[bi]) - s * S["depth_atr"] * a
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
        fee = (0.0002 + (0.0002 if kind == "take" else 0.0005) + 0.0003 * (kk + 1) * S["tfh"] / 24) * fill
        r = (s * (exv - fill) - fee) / risk
        if abs(r - float(X["R"][S["ex"]][i])) > 1e-3: print("mismatch", S["name"], sym, r, X["R"][S["ex"]][i])
        bs = S["tfh"] * 3600
        EV.append(dict(ft=int(Tb[fb]), nsc=-float(SC[i]), t=t, sym=sym, s=s, end=int(Tb[fb + kk]) + bs, r=float(r), w=int(kind == "take"),
                       st=S["name"], c=f"{S['tfh']}h", lv=lv, fill=fill, sl=sl, tp=tp, xp=float(exv), k=kind, t1=int(Tb[bi + 1]),
                       un=bool(X["chk"][i] or X["new"][i]), stop=float(np.clip(2 * a / fill, 0.002, 0.5))))
# ---- the pool as the bot trades it ----
EV.sort(key=lambda e: (e["ft"], e["nsc"], e["t"]))
busy, act, pool = {}, [], []
for e in EV:
    if busy.get((e["sym"], e["s"]), 0) > e["ft"]: continue
    act = [x for x in act if x[0] > e["ft"]]
    if sum(1 for x in act if x[1] == e["s"]) >= CAP: continue
    busy[(e["sym"], e["s"])] = e["end"]; act.append((e["end"], e["s"])); pool.append(e)
np.save("pool689.npy", np.array([(e["ft"], e["end"], e["r"], e["stop"]) for e in pool], float))
years = {}
for e in pool:
    part = "unseen" if e["un"] else "train"; Y = str(1970 + e["ft"] // 31557600)
    d = years.setdefault(part, {}).setdefault(Y, {"n": 0, "sum": 0.0, "w": 0, "st": {}}); d["n"] += 1; d["sum"] += e["r"]; d["w"] += e["w"]
    d["st"][e["st"]] = d["st"].get(e["st"], 0) + 1
for part in years:
    for Y, d in years[part].items():
        mo = ((ts(int(Y) + 1) if int(Y) < 2026 else ts(2026, 10)) - ts(int(Y))) / (30.4 * 86400)
        years[part][Y] = {"n": d["n"], "avg": round(d["sum"] / d["n"], 3), "wr": round(d["w"] / d["n"] * 100, 1), "pm": round(d["n"] / mo, 1), "streams": d["st"]}
out = []
for e in pool:
    if e["ft"] < ts(2025): continue
    gs, scl = gate_sym(e["sym"])
    out.append({"s": gs, "d": e["s"], "c": e["c"], "st": e["st"], "t": e["t1"], "lv": round(e["lv"] / scl, 10), "e": round(e["fill"] / scl, 10),
                "sl": round(e["sl"] / scl, 10), "tp": round(e["tp"] / scl, 10), "f": e["ft"], "x": e["end"], "xp": round(e["xp"] / scl, 10),
                "r": round(e["r"], 3), "k": e["k"], "chk": e["un"]})
out.sort(key=lambda x: x["t"])
json.dump(out, open("dlm_bt_v689.json", "w"), separators=(",", ":"))
un = [e for e in pool if e["un"]]; h = [e for e in un if e["ft"] >= ts(2025, 10)]
print("backtest list", len(out), "avg", round(np.mean([x["r"] for x in out]), 3), "wr", round(np.mean([x["k"] == "take" for x in out]) * 100, 1),
      {n: sum(1 for x in out if x["st"] == n) for n in ("wick4h", "close2h")}, "pool", len(pool))
M = {"ver": 3, "kind": "dlm", "feats": FN, "streams": out_streams, "q": Q, "side_cap": CAP, "trained_to": int(ts(2026) - 3 * 86400),
     "rule": {"min_bars": 2000, "depth_min": 0.3, "depth_max": 6.0},
     "research": {"coins": 210, "train_coins": 85, "check_coins": 42, "new_coins": 82, "models_n": 20, "years": years,
                  "unseen": {"wr": round(np.mean([e["w"] for e in un]) * 100), "avg": round(float(np.mean([e["r"] for e in un])), 3),
                             "last12_wr": round(np.mean([e["w"] for e in h]) * 100), "last12_avg": round(float(np.mean([e["r"] for e in h])), 3)},
                  "m1": {"wr": 82, "avg_through": 0.24},
                  "money": {"pos": 20, "risk": 4.0}}}
json.dump(M, open("vp_dlm_model_v3.json", "w"), separators=(",", ":"))
print("model size", os.path.getsize("vp_dlm_model_v3.json"), json.dumps(M["research"]["unseen"]), json.dumps(years))
