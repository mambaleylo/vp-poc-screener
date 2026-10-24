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
import os
HOLDP, TAKE_ = int(os.environ.get('PHD', 48)), float(os.environ.get('PTK', 4.5))
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
    hs, ss, tp = e - s * HARD * a, e - s * SOFT * a, e + s * TAKE_ * a
    kind, kx, ex = "time", min(HOLDP, len(C) - f) - 1, C[min(f + HOLDP, len(C)) - 1]
    for q in range(min(HOLDP, len(C) - f)):
        b = f + q
        if (L[b] <= hs) if s > 0 else (H[b] >= hs): kind, kx, ex = "hard", q, hs; break
        if (H[b] >= tp) if s > 0 else (L[b] <= tp): kind, kx, ex = "take", q, tp; break
        if (C[b] <= ss) if s > 0 else (C[b] >= ss): kind, kx, ex = "stop", q, C[b]; break
    rr = (s * (ex - e) - e * 0.001 - e * 0.0003 * (kx + 1) / 24) / (HARD * a)
    if abs(rr - RJ) > 0.02: bad += 1
    gs, sc = gate_sym(sym)
    out.append({"s": gs, "d": s, "c": "1h", "t": int(T[i + 1]), "e": round(e / sc, 10), "lv": round(lv / sc, 10), "f": int(T[f]), "sl": round(ss / sc, 10),
                "tp": round(tp / sc, 10), "hs": round(hs / sc, 10), "x": int(T[f + kx] + 3600), "xp": round(float(ex) / sc, 10), "r": round(float(rr), 3), "k": kind})

rs = np.array([x["r"] for x in out]); yy = np.array([int(np.datetime64(x["t"], "s").astype("datetime64[Y]").astype(int) + 1970) for x in out])
print(f"P/R тейк {TAKE_} ATR, {HOLDP}ч: {len(rs)} сделок {rs.mean():+.3f}R WR {np.mean(rs > 0)*100:.0f}% | " + " ".join(f"{Y % 100}:{rs[yy == Y].mean():+.2f}" for Y in range(2023, 2027)))
json.dump(out, open(f"prv_x_{TAKE_}_{HOLDP}.json", "w"), separators=(",", ":"))
