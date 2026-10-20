"""🌊 cascade v0.99.654 (the user: "подряд по 15 сделок в минус"): a third of the position off at +0.7R, the stop to the
entry, the rest to the take 2.5R, out after 48 h, at most 6 per side. On the 3-model walk-forward scores (cas_sel3.py
TAG=base3 SEEDS=3 = how the exported model is built). The yearly stats and the bot's backtest list."""
import os, sys, json, numpy as np
os.environ.setdefault("CAS_SEL", "cas_sel_base3.npz")
from numba import njit
from cas_h import S, SD, T, SY, YR, SYMS, bars
from bt_trades import gate_sym
from wr_eval import streaks
from mk import ts
RULE = dict(take_r=2.5, hold=48, part_r=0.7, part_f=0.33, cap=6)
@njit(cache=True)
def sim(O, H, L, C, i, s, a, take_r, hold, part_r, part_f):
    """entry O[i+1]; the stop at the 24-bar swing ± 0.2 ATR on touch (a gap fills at the open); the partial at +part_r R
    (the stop to the entry); the take; out at the hold's last close. -> R (fees on the whole), bars, exit, kind, partial"""
    n = len(C); e = O[i + 1]
    lo = L[i]; hi = H[i]
    for k in range(max(0, i - 23), i + 1):
        lo = min(lo, L[k]); hi = max(hi, H[k])
    stop = (lo - 0.2 * a) if s > 0 else (hi + 0.2 * a)
    risk = s * (e - stop)
    if risk <= e * 0.002 or hold > n - i - 2: return np.nan, 0, 0.0, 0, False, stop
    tp = e + s * take_r * risk; st = stop; took = False; k = hold - 1; px = C[i + hold]; kind = 3
    for q in range(hold):
        b = i + 1 + q
        if (L[b] <= st) if s > 0 else (H[b] >= st):
            gap = q > 0 and ((O[b] <= st) if s > 0 else (O[b] >= st))
            px = O[b] if gap else st; k = q; kind = 1 if took else 0; break
        if part_r > 0 and not took and ((H[b] - e) if s > 0 else (e - L[b])) >= part_r * risk:
            took = True; st = e
        if (H[b] >= tp) if s > 0 else (L[b] <= tp):
            px = tp; k = q; kind = 2; break
    fee = (0.001 + 0.0003 * (k + 1) / 24) * e / risk
    rest = s * (px - e) / risk
    return ((part_f * part_r + (1 - part_f) * rest) if took else rest) - fee, k + 1, px, kind, took, stop
def trades(q, take_r=2.5, hold=48, part_r=0.7, part_f=0.33, cap=6):
    ev = []
    for s in (1, -1):
        sc = S[f"sc_sw_t2_48_{s}"]
        if f"thrv_sw_t2_48_{s}_{q}" in S.files: tv = S[f"thrv_sw_t2_48_{s}_{q}"]
        else:
            thr = np.array([S[f"thr_sw_t2_48_{s}_{q}_{y}"] if f"thr_sw_t2_48_{s}_{q}_{y}" in S.files else np.inf for y in range(2000, 2030)]); tv = thr[np.clip(YR - 2000, 0, 29)]
        for r in np.where((SD == s) & ~np.isnan(sc) & (sc >= tv))[0]: ev.append((int(T[r]), -float(sc[r]), int(SY[r]), s, int(r)))
    ev.sort(); busy, act, out = {}, [], []
    for t, _, sy, s, r in ev:
        if busy.get((sy, s), 0) > t: continue
        act = [x for x in act if x[0] > t]
        if sum(1 for x in act if x[1] == s) >= cap: continue
        O, H, L, C, TOP, BOT, atr, tm = bars(sy); i = int(np.searchsorted(tm, t))
        if i >= len(tm) or tm[i] != t: continue
        R, k, px, kind, took, stop = sim(O, H, L, C, i, s, atr[i], take_r, hold, part_r, part_f)
        if R != R: continue
        end = t + 3600 * (k + 1); busy[(sy, s)] = end; act.append((end, s))
        out.append((t, end, float(R), s, r, i, sy, float(px), int(kind), bool(took), float(stop)))
    return out
if __name__ == "__main__":
    tr = [x for x in trades(0.995, **{k: v for k, v in RULE.items()}) if x[0] >= ts(2022)]
    years = {}
    for y in (2022, 2023, 2024, 2025):
        hi = ts(y + 1) if y < 2025 else ts(2027)
        o = sorted([x for x in tr if ts(y) <= x[1] < hi], key=lambda x: x[1]); rs = np.array([x[2] for x in o]); c = np.r_[0, np.cumsum(rs)]
        wk = ((ts(y + 1) if y < 2025 else ts(2026, 10)) - ts(y)) / (7 * 86400)
        years[str(y)] = {"n": len(rs), "avg": round(float(rs.mean()), 3), "wk": round(len(rs) / wk, 1), "sum": round(float(rs.sum()), 1),
                         "dd": round(float(np.max(np.maximum.accumulate(c) - c)), 1), "wr": round(float((rs > 0).mean() * 100), 1)}
        print(y, years[str(y)])
    mx, n8 = streaks([x[:5] for x in tr]); print("max losing run", mx, "runs 8+", n8)
    json.dump({"years": years, "max_losing_streak": mx}, open("cas_years_v654.json", "w"))
    KN = {0: "stop", 1: "be", 2: "take", 3: "time"}; res = []
    for t, end, r, s, row, i, sy, px, kind, took, stop in tr:
        O, H, L, C, TOP, BOT, atr, tm = bars(sy); e = O[i + 1]; risk = s * (e - stop); gs, scl = gate_sym(SYMS[sy])
        res.append({"s": gs, "d": s, "c": "1h", "t": int(t), "e": round(e / scl, 10), "sl": round(stop / scl, 10), "tp": round((e + s * RULE["take_r"] * risk) / scl, 10),
                    "pt": round((e + s * RULE["part_r"] * risk) / scl, 10), "x": int(end - 3600), "xp": round(px / scl, 10), "r": round(r, 3), "k": KN[kind], "part": took})
    from collections import Counter
    print(len(res), Counter(x["k"] for x in res), "WR", np.mean([x["r"] > 0 for x in res]))
    json.dump(res, open("cas_bt_v654.json", "w"), separators=(",", ":"))
