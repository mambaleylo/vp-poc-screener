"""audit of P/R like ⚡: the pool's order inside an hour — the score (the list) vs random"""
"""P/R v0.99.670 (more trades): the same rule on 211 coins (the 127 + 84 Binance coins with >= 150M $ a month, prmore.py) and
at most 20 open per side (was 12): 2023-26 1.8 trades a week instead of 1.2, the years +0.43 / +0.36 / +0.51 / +0.23R vs
+0.39 / +0.36 / +0.57 / +0.24R, x7400 vs x1800 at an equal drawdown. Was: P/R v0.99.662: the entry by a limit 0.3 ATR better than the next bar's open, waiting 3 bars (no fill = no trade); the
rest as deployed (stop by the 1h close 3 ATR, hard 6, take 4.5 ATR, 48 bars, R per the hard stop). The bot's list
(q 0.99, 1h, both BTC filters, cap 12) with the fills / exits re-derived, the yearly stats, the model ver 7."""
import os, glob, json, numpy as np
import pr_hyp as P
import prv_wf as W
from pr_x_eval import cands
from common import V, load
from bt_trades import gate_sym
LIM, WAIT, SOFT, HARD, TAKE = 0.3, 3, 3.0, 6.0, 4.5
import prmore as PM
trl = PM.trades([PM.OLD, PM.NEW], 0.99, cap=20)
SETS = [PM.OLD, PM.NEW]
cache = {}; out = []; bad = 0
KN = {0: "hard", 1: "stop", 2: "take", 3: "time"}
for x_ in trl:
    D_ = SETS[x_[4][0]]; j = x_[4][1]; RJ = float(D_["R"][j])
    sym = str(D_["SY"][j]); s = int(D_["SD"][j]); t = int(D_["T"][j])
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
    if abs(rr - RJ) > 0.02: bad += 1
    gs, sc = gate_sym(sym)
    out.append({"s": gs, "d": s, "c": "1h", "t": int(T[i + 1]), "e": round(e / sc, 10), "lv": round(lv / sc, 10), "f": int(T[f]), "sl": round(ss / sc, 10),
                "tp": round(tp / sc, 10), "hs": round(hs / sc, 10), "x": int(T[f + kx] + 3600), "xp": round(float(ex) / sc, 10), "r": round(RJ, 3), "k": kind})
print("trades", len(out), "R mismatches", bad)
from mk import ts
years = {}
for Y in (2023, 2024, 2025):
    rs = np.array([x["r"] for x in out if (ts(Y) <= x["x"] < ts(Y + 1)) or (Y == 2025 and x["x"] >= ts(2026))]); c = np.r_[0, np.cumsum(rs)]
    wk = ((ts(Y + 1) if Y < 2025 else ts(2026, 10)) - ts(Y)) / 604800
    years[str(Y)] = {"n": len(rs), "avg": round(float(rs.mean()), 3), "wk": round(len(rs) / wk, 1), "sum": round(float(rs.sum()), 1),
                     "dd": round(float(np.max(np.maximum.accumulate(c) - c)), 1), "wr": round(float((rs > 0).mean() * 100), 1)}
    print(Y, years[str(Y)])
out.sort(key=lambda x: x["t"]); json.dump(out, open("prv_bt_v670.json", "w"), separators=(",", ":"))
m = json.load(open("/home/user/vp-poc-screener/vp_prv_model.json"))
m["ver"] = 8; m["side_cap"] = 20; m["research"].update({"years": years, "coins": 211, "cap": 20})
json.dump(m, open("vp_prv_model_v8.json", "w"), separators=(",", ":"))
print("rule", m["rule"])

# ---- pr_order: the hour's signals ordered by the score (the list) vs random (the touches of the limits come in any order)
C_ = cands("99")
def rep(key, cap=20):
    o = C_[np.lexsort((key[C_], P.T[C_]))]
    busy, act, out = {}, [], []
    for j in o:
        t = P.T[j]; k = (P.SY[j], P.SD[j])
        if busy.get(k, 0) > t or P.R[j] != P.R[j]: continue
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == P.SD[j]) >= cap: continue
        busy[k] = P.END[j]; act.append((P.END[j], P.SD[j])); out.append(j)
    return np.array(out, dtype=int)
def show(nm, tr):
    rr = P.R[tr]
    ys = " ".join(f"{y % 100}:{rr[(P.T[tr] >= P.ts(y)) & (P.T[tr] < P.ts(y + 1))].mean():+.2f}" for y in (2023, 2024, 2025, 2026))
    print(f"{nm:30s} сделок {len(tr):4d} {rr.mean():+.3f}R WR {np.mean(rr > 0)*100:.0f}% | {ys}", flush=True)
nh = {}
for j in C_: nh[(P.T[j], P.SD[j])] = nh.get((P.T[j], P.SD[j]), 0) + 1
print("кандидатов", len(C_), "· часов с > 1 сигналом в сторону:", sum(1 for v in nh.values() if v > 1), "из", len(nh))
show("по баллу (как в списке)", rep(-P.SC_OF))
rng = np.random.default_rng(1)
for k in range(3): show(f"случайный #{k + 1}", rep(rng.random(len(P.T))))
