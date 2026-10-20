"""P/R v0.99.662: the entry by a limit 0.3 ATR better than the next bar's open, waiting 3 bars (no fill = no trade); the
rest as deployed (stop by the 1h close 3 ATR, hard 6, take 4.5 ATR, 48 bars, R per the hard stop). The bot's list
(q 0.99, 1h, both BTC filters, cap 12) with the fills / exits re-derived, the yearly stats, the model ver 7."""
import os, glob, json, numpy as np
import pr_hyp as P
import prv_wf as W
from pr_x_eval import cands
from common import V, load
from bt_trades import gate_sym
LIM, WAIT, SOFT, HARD, TAKE = 0.3, 3, 3.0, 6.0, 4.5
z = np.load(f"{W.D}/px_lim3_3.npz"); r = z["cs"].astype(float)
P.R = np.where(np.abs(r) > 20, np.nan, r); P.KIND = z["kind"]; P.END = P.T + (z["k"].astype(int) + 1) * P.TF * 3600
tr = P.replay(cands("99"))
files = sorted(glob.glob(f"{W.D}/prv_ev/*.npz")); syms = [os.path.basename(f)[:-4] for f in files if len(np.load(f)["t"])]
cache = {}; out = []; bad = 0
KN = {0: "hard", 1: "stop", 2: "take", 3: "time"}
for j in tr:
    sym = syms[int(W.SY[j])]; s = int(W.SD[j]); t = int(W.T[j])
    if sym not in cache:
        cs = load(sym); cache.clear()
        cache[sym] = (np.array([c["open"] for c in cs]), np.array([c["high"] for c in cs]), np.array([c["low"] for c in cs]), np.array([c["close"] for c in cs]),
                      np.array([c["time"] for c in cs]), np.array([a if a else np.nan for a in V.neuro_atr_series(cs, 14)]))
    O, H, L, C, T, A = cache[sym]
    i = int(np.searchsorted(T, t - 3600)); a = A[i]
    lv = O[i + 1] - s * LIM * a
    f = next(b for b in range(i + 1, i + 1 + WAIT) if ((L[b] <= lv) if s > 0 else (H[b] >= lv)))
    e = min(lv, O[f]) if s > 0 else max(lv, O[f])
    hs, ss, tp = e - s * HARD * a, e - s * SOFT * a, e + s * TAKE * a
    kind, kx, ex = "time", 47, C[f + 47]
    for q in range(48):
        b = f + q
        if (L[b] <= hs) if s > 0 else (H[b] >= hs): kind, kx, ex = "hard", q, hs; break
        if (H[b] >= tp) if s > 0 else (L[b] <= tp): kind, kx, ex = "take", q, tp; break
        if (C[b] <= ss) if s > 0 else (C[b] >= ss): kind, kx, ex = "stop", q, C[b]; break
    rr = (s * (ex - e) - e * 0.001 - e * 0.0003 * (kx + 1) / 24) / (HARD * a)
    if abs(rr - P.R[j]) > 0.02: bad += 1
    gs, sc = gate_sym(sym)
    out.append({"s": gs, "d": s, "c": "1h", "t": int(T[i + 1]), "e": round(e / sc, 10), "lv": round(lv / sc, 10), "f": int(T[f]), "sl": round(ss / sc, 10),
                "tp": round(tp / sc, 10), "hs": round(hs / sc, 10), "x": int(T[f + kx] + 3600), "xp": round(float(ex) / sc, 10), "r": round(float(P.R[j]), 3), "k": kind})
print("trades", len(out), "R mismatches", bad)
from mk import ts
years = {}
for Y in (2023, 2024, 2025):
    rs = np.array([x["r"] for x in out if (ts(Y) <= x["x"] < ts(Y + 1)) or (Y == 2025 and x["x"] >= ts(2026))]); c = np.r_[0, np.cumsum(rs)]
    wk = ((ts(Y + 1) if Y < 2025 else ts(2026, 10)) - ts(Y)) / 604800
    years[str(Y)] = {"n": len(rs), "avg": round(float(rs.mean()), 3), "wk": round(len(rs) / wk, 1), "sum": round(float(rs.sum()), 1),
                     "dd": round(float(np.max(np.maximum.accumulate(c) - c)), 1), "wr": round(float((rs > 0).mean() * 100), 1)}
    print(Y, years[str(Y)])
json.dump(out, open("prv_bt_v662.json", "w"), separators=(",", ":"))
m = json.load(open("/home/user/vp-poc-screener/vp_prv_model.json"))
m["ver"] = 7; m["rule"].update({"entry_lim_atr": LIM, "entry_wait": WAIT}); m["research"]["years"] = years
json.dump(m, open("vp_prv_model_v7.json", "w"), separators=(",", ":"))
print("rule", m["rule"])
