"""📈 breakout v0.99.654: a quarter of the position off at +1R, the stop to the entry, the rest by the trend (stop 2 ATR,
20-bar channel, 15 after +4R, 6 per side per chart). The yearly stats per chart (the bot's RBX_RESEARCH "<hrs>_part")
and the backtest list (vp_bt_trades.json "rbx") from 2021."""
import json, numpy as np, datetime as dt
from numba import njit
import rb_h as B
from rb_sim2 import bars, NEX
from bt_trades import gate_sym
from mk import ts
PART_R, PART_F = 1.0, 0.25
@njit(cache=True)
def sim(O, H, L, C, LO, HI, i0, e, s, a, hold, tfh, ne, ne2, part_r, part_f):
    """-> R (fees on the whole position), bars, exit price, kind (0 stop, 1 break-even, 2 trend, 3 time), the partial taken"""
    n = len(C); risk = 2.0 * a; hs = e - s * risk
    tight = False; best = 0.0; took = False
    W = min(hold, n - i0); k = W - 1; ex = C[i0 + k]; kind = 3
    for q in range(W):
        b = i0 + q
        if (s > 0 and L[b] <= hs) or (s < 0 and H[b] >= hs):
            ex = hs if q == 0 or not ((s > 0 and O[b] <= hs) or (s < 0 and O[b] >= hs)) else O[b]; k = q; kind = 1 if took else 0; break
        fav = (H[b] - e) / risk if s > 0 else (e - L[b]) / risk
        if fav > best: best = fav
        if part_r > 0 and not took and best >= part_r:
            took = True; hs = e
        if best >= 4.0: tight = True
        lv = LO[ne2 if tight else ne, b] if s > 0 else HI[ne2 if tight else ne, b]
        if (s > 0 and C[b] < lv) or (s < 0 and C[b] > lv):
            ex = C[b]; k = q; kind = 2; break
    fee = (0.001 * e + 0.0003 * e * (k + 1) * tfh / 24) / risk
    rest = s * (ex - e) / risk
    return ((part_f * part_r + (1 - part_f) * rest) if took else rest) - fee, k + 1, ex, kind, took
def run(mask, cap=6, part_r=PART_R, part_f=PART_F):
    R = np.full(len(B.T), np.nan); Hh = np.ones(len(B.T), np.int64); EX = {}
    for i in np.where(mask & (B.T >= B.START))[0]:
        tfh = int(B.TF[i]); O, H, L, C, T, atr, LO, HI, e200 = bars(B.SYM[i], tfh)
        j = int(np.searchsorted(T, B.T[i]))
        if j >= len(T) - 2 or T[j] != B.T[i] or atr[j] != atr[j]: continue
        r, k, ex, kind, took = sim(O, H, L, C, LO, HI, j + 1, O[j + 1], int(B.SD[i]), float(atr[j]), 180 if tfh == 24 else 360, tfh,
                                   NEX.index(20), NEX.index(15), part_r, part_f)
        R[i], Hh[i] = r, k; EX[i] = (j, ex, kind, took)
    return B.replay(mask, R, Hh, cap=cap), R, Hh, EX
if __name__ == "__main__":
    YRS = (2021, 2022, 2023, 2024, 2025)
    WK = {y: ((ts(y + 1) if y < 2025 else ts(2026, 10)) - ts(y)) / (7 * 86400) for y in YRS}
    OUT, bt = {}, []
    KN = {0: "stop", 1: "be", 2: "trend", 3: "time"}
    for tfh, ch, n0 in ((24, "1d", 20), (12, "12h", 30)):
        tr, R, Hh, EX = run(B.BOT & (B.TF == tfh))
        T_ = B.T[tr]; end = T_ + Hh[tr] * tfh * 3600; r = R[tr]
        years = {}
        for y in YRS:
            m = (end >= ts(y)) & (end < (ts(y + 1) if y < 2025 else ts(2027)))
            rs = r[m][np.argsort(end[m])]; c = np.r_[0, np.cumsum(rs)]
            years[str(y)] = {"n": int(m.sum()), "avg": round(float(rs.mean()), 2), "wk": round(m.sum() / WK[y], 1), "sum": round(float(rs.sum()), 1),
                             "dd": round(float(np.max(np.maximum.accumulate(c) - c)), 1), "wr": round(float((rs > 0).mean() * 100), 1),
                             "days": round(float(Hh[tr][m].mean() * tfh / 24), 0), "best": round(float(rs.max()), 1)}
        o = np.argsort(end); run_ = mx = 0
        for v in r[o]: run_ = run_ + 1 if v < 0 else 0; mx = max(mx, run_)
        OUT[f"{tfh}_part"] = {"years": years, "max_losing_streak": int(mx)}
        print(tfh, f"{r.mean():+.3f}R WR{(r > 0).mean()*100:.0f}% n{len(r)} серия{mx}", years, flush=True)
        for i in tr:
            j, ex, kind, took = EX[i]; O, H, L, C, T, atr, LO, HI, e200 = bars(B.SYM[i], tfh); s = int(B.SD[i])
            e = O[j + 1]; risk = 2.0 * atr[j]; gs, sc = gate_sym(B.SYM[i])
            hh, ll = H[j - n0:j].max(), L[j - n0:j].min()
            bt.append({"s": gs, "d": s, "c": ch, "t": int(T[j]), "e": round(e / sc, 10), "sl": round((e - s * risk) / sc, 10), "pt": round((e + s * PART_R * risk) / sc, 10),
                       "x": int(T[j + Hh[i]]), "xp": round(float(ex) / sc, 10), "r": round(float(R[i]), 3), "k": KN[kind], "part": bool(took),
                       "hh": round(hh / sc, 10), "ll": round(ll / sc, 10), "n": n0, "t0": int(T[j - n0] - tfh * 3600)})
    json.dump(OUT, open("rbx_research_v654.json", "w"), separators=(",", ":"))
    json.dump(bt, open("rbx_bt_v654.json", "w"), separators=(",", ":"))
    from collections import Counter
    print(len(bt), Counter(x["k"] for x in bt))
