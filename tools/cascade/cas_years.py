"""the research stats per year (q 0.995 walk-forward, cas_sel.npz) + the bot's backtest list (vp_bt_trades.json "csx")"""
import json, numpy as np
from cas_h import trades, SYMS, SD, bars, ts
from bt_trades import gate_sym
tr = [x for x in trades("sw_t2_48", 0.995) if x[0] >= ts(2022)]
years = {}
for y in (2022, 2023, 2024, 2025):
    hi = ts(y + 1) if y < 2025 else ts(2027)
    rs = np.array([x[2] for x in sorted(tr, key=lambda x: x[1]) if ts(y) <= x[1] < hi]); c = np.r_[0, np.cumsum(rs)]
    wk = ((ts(y + 1) if y < 2025 else ts(2026, 10)) - ts(y)) / (7 * 86400)
    years[str(y)] = {"n": len(rs), "avg": round(float(rs.mean()), 3), "wk": round(len(rs) / wk, 1), "sum": round(float(rs.sum()), 1),
                     "dd": round(float(np.max(np.maximum.accumulate(c) - c)), 1), "wr": round(float((rs > 0).mean() * 100), 1)}
    print(y, years[str(y)])
json.dump(years, open("cas_years.json", "w"))
import cas_h
res = []
for t, end, r, s, row in tr:
    sy = int(cas_h.SY[row]); O, H, L, C, TOP, BOT, atr, tm = bars(sy); i = int(np.searchsorted(tm, t))
    a = atr[i]; lo, hi = L[max(0, i - 23):i + 1].min(), H[max(0, i - 23):i + 1].max()
    stop = lo - 0.2 * a if s > 0 else hi + 0.2 * a; e = O[i + 1]; risk = s * (e - stop); tp = e + s * 2 * risk
    kind, kx, xp = "time", 47, C[i + 48]
    for q in range(48):
        bb = i + 1 + q
        if (L[bb] <= stop) if s > 0 else (H[bb] >= stop):
            kind, kx, xp = "stop", q, (O[bb] if (q > 0 and ((s > 0 and O[bb] <= stop) or (s < 0 and O[bb] >= stop))) else stop); break
        if (H[bb] >= tp) if s > 0 else (L[bb] <= tp):
            kind, kx, xp = "take", q, tp; break
    rr = (s * (xp - e) - (0.001 + 0.0003 * (kx + 1) / 24) * e) / risk
    assert abs(rr - r) < 1e-3 and (end - t) // 3600 - 2 == kx, (rr, r)
    ex_t = int(tm[i + 1 + kx])
    gs, scl = gate_sym(SYMS[sy])
    res.append({"s": gs, "d": s, "c": "1h", "t": int(t), "e": round(e / scl, 10), "sl": round(stop / scl, 10), "tp": round(tp / scl, 10),
                "x": ex_t, "xp": round(float(xp) / scl, 10), "r": round(r, 3), "k": kind, "sc": None})
from collections import Counter
print(len(res), Counter(x["k"] for x in res))
json.dump(res, open("cas_bt.json", "w"), separators=(",", ":"))
