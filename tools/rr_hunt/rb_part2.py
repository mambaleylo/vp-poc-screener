"""📈 breakout v0.99.655: only strong breakouts (the close ≥ 0.6 ATR beyond the range) and out at the close back inside
the range within the first 2 bars (the user: "часто в стопах, когда идёт сразу после входа только в сторону стопа");
a quarter at +1R as before. The yearly stats per chart (with and without the partial) and the backtest list."""
import json, numpy as np
import rb_h as B
from rb_sim2 import bars, NEX
from rb_fail import sim
from bt_trades import gate_sym
from mk import ts
MIN_BRK, FAIL_K = 0.6, 2
YRS = (2021, 2022, 2023, 2024, 2025)
WK = {y: ((ts(y + 1) if y < 2025 else ts(2026, 10)) - ts(y)) / (7 * 86400) for y in YRS}
KN = {0: "stop", 1: "be", 2: "trend", 3: "time", 4: "fail"}
OUT, bt = {}, []
for tfh, ch, n0 in ((24, "1d", 20), (12, "12h", 30)):
    for part in (True, False):
        mask = B.BOT & (B.TF == tfh) & (B.BRK >= MIN_BRK)
        R = np.full(len(B.T), np.nan); Hh = np.ones(len(B.T), np.int64); EX = {}
        for i in np.where(mask & (B.T >= B.START))[0]:
            O, H, L, C, T, atr, LO, HI, e200 = bars(B.SYM[i], tfh)
            j = int(np.searchsorted(T, B.T[i]))
            if j >= len(T) - 4 or T[j] != B.T[i] or atr[j] != atr[j]: continue
            s = int(B.SD[i]); lvl = H[j - n0:j].max() if s > 0 else L[j - n0:j].min()
            r, k, kind, best = sim(O, H, L, C, LO, HI, j + 1, O[j + 1], s, 2.0 * float(atr[j]), 180 if tfh == 24 else 360, tfh,
                                   NEX.index(20), NEX.index(15), 1.0 if part else 0.0, 0.25, lvl, FAIL_K, 0.0)
            R[i], Hh[i] = r, k; EX[i] = (j, kind, lvl)
        tr = B.replay(mask, R, Hh, cap=6)
        T_ = B.T[tr]; end = T_ + Hh[tr] * tfh * 3600; r = R[tr]
        years = {}
        for y in YRS:
            m = (end >= ts(y)) & (end < (ts(y + 1) if y < 2025 else ts(2027)))
            rs = r[m][np.argsort(end[m])]; c = np.r_[0, np.cumsum(rs)]
            years[str(y)] = {"n": int(m.sum()), "avg": round(float(rs.mean()), 2), "wk": round(float(m.sum() / WK[y]), 1), "sum": round(float(rs.sum()), 1),
                             "dd": round(float(np.max(np.maximum.accumulate(c) - c)), 1), "wr": round(float((rs > 0).mean() * 100), 1),
                             "days": round(float(Hh[tr][m].mean() * tfh / 24), 0), "best": round(float(rs.max()), 1)}
        o = np.argsort(end); run_ = mx = 0
        for v in r[o]: run_ = run_ + 1 if v < 0 else 0; mx = max(mx, run_)
        OUT[f"{tfh}_{'part' if part else 'dc20'}"] = {"years": years, "max_losing_streak": int(mx)}
        print(tfh, "part" if part else "без", f"{r.mean():+.3f}R WR{(r > 0).mean()*100:.0f}% n{len(r)} серия{mx}", flush=True)
        if not part: continue
        for i in tr:
            j, kind, lvl = EX[i]; O, H, L, C, T, atr, LO, HI, e200 = bars(B.SYM[i], tfh); s = int(B.SD[i])
            e = O[j + 1]; risk = 2.0 * atr[j]; gs, sc = gate_sym(B.SYM[i]); k = Hh[i]
            ex = C[j + k] if kind in (2, 3, 4) else None
            if ex is None:   # a stop: the stop level or the gap open; back from R
                fee = (0.001 * e + 0.0003 * e * k * tfh / 24) / risk
                rr = R[i] + fee; took = kind == 1
                ex = e + s * ((rr - 0.25) / 0.75 if took else rr) * risk
            hh, ll = H[j - n0:j].max(), L[j - n0:j].min()
            bt.append({"s": gs, "d": s, "c": ch, "t": int(T[j]), "e": round(e / sc, 10), "sl": round((e - s * risk) / sc, 10), "pt": round((e + s * risk) / sc, 10),
                       "x": int(T[j + k]), "xp": round(float(ex) / sc, 10), "r": round(float(R[i]), 3), "k": KN[kind], "fk": FAIL_K,
                       "hh": round(hh / sc, 10), "ll": round(ll / sc, 10), "n": n0, "t0": int(T[j - n0] - tfh * 3600)})
json.dump(OUT, open("rbx_research_v655.json", "w"), separators=(",", ":"))
json.dump(bt, open("rbx_bt_v655.json", "w"), separators=(",", ":"))
from collections import Counter
print(len(bt), Counter(x["k"] for x in bt))
