"""📈 breakout v0.99.667: + no trade when the crowd (Binance, all accounts' long/short ratio) moved 24h into the trade's
side by more than LS_MAX (log; mfeat.py ls_d24 × side, the top third of the bot's set before 2023); no data = trade.
v0.99.663: + the entry by a limit 0.2 ATR better than the entry bar's open, waiting 3 bars;
v0.99.655: only strong breakouts (the close ≥ 0.6 ATR beyond the range) and out at the close back inside
the range within the first 2 bars (the user: "часто в стопах, когда идёт сразу после входа только в сторону стопа");
a quarter at +1R as before. The yearly stats per chart (with and without the partial) and the backtest list."""
import json, numpy as np
import rb_h as B
from rb_sim2 import bars, NEX
from rb_fail import sim
from bt_trades import gate_sym
from mk import ts
MIN_BRK, FAIL_K = 0.6, 2
LS_MAX = 0.0918
import mfeat
LS = mfeat.at(B.SYM, B.T + B.TF * 3600 - 3600)[:, mfeat.NAMES.index('ls_d24')] * B.SD
CROWD_OK = ~(LS > LS_MAX)
LIM, WAIT = 0.2, 3
YRS = (2021, 2022, 2023, 2024, 2025)
WK = {y: ((ts(y + 1) if y < 2025 else ts(2026, 10)) - ts(y)) / (7 * 86400) for y in YRS}
KN = {0: "stop", 1: "be", 2: "trend", 3: "time", 4: "fail"}
OUT, bt = {}, []
for tfh, ch, n0 in ((24, "1d", 20), (12, "12h", 30)):
    for part in (True, False):
        mask = B.BOT & (B.TF == tfh) & (B.BRK >= MIN_BRK) & CROWD_OK
        R = np.full(len(B.T), np.nan); Hh = np.ones(len(B.T), np.int64); EX = {}
        for i in np.where(mask & (B.T >= B.START))[0]:
            O, H, L, C, T, atr, LO, HI, e200 = bars(B.SYM[i], tfh)
            j = int(np.searchsorted(T, B.T[i]))
            if j >= len(T) - 4 or T[j] != B.T[i] or atr[j] != atr[j]: continue
            s = int(B.SD[i]); lvl = H[j - n0:j].max() if s > 0 else L[j - n0:j].min()
            lv = O[j + 1] - s * LIM * float(atr[j]); f = next((j + q for q in range(1, WAIT + 1) if j + q < len(C) and ((L[j + q] <= lv) if s > 0 else (H[j + q] >= lv))), None)
            if f is None: continue
            e = min(O[f], lv) if s > 0 else max(O[f], lv)
            r, k, kind, best = sim(O, H, L, C, LO, HI, f, e, s, 2.0 * float(atr[j]), 180 if tfh == 24 else 360, tfh,
                                   NEX.index(20), NEX.index(15), 1.0 if part else 0.0, 0.25, lvl, FAIL_K, 0.0)
            R[i], Hh[i] = r, k + (f - j - 1); EX[i] = (j, kind, lvl, f, e)
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
            j, kind, lvl, f, e = EX[i]; O, H, L, C, T, atr, LO, HI, e200 = bars(B.SYM[i], tfh); s = int(B.SD[i])
            risk = 2.0 * atr[j]; gs, sc = gate_sym(B.SYM[i]); k = Hh[i]; kk = k - (f - j - 1)
            ex = C[j + k] if kind in (2, 3, 4) else None
            if ex is None:   # a stop: the stop level or the gap open; back from R
                fee = (0.001 * e + 0.0003 * e * kk * tfh / 24) / risk
                rr = R[i] + fee; took = kind == 1
                ex = e + s * ((rr - 0.25) / 0.75 if took else rr) * risk
            hh, ll = H[j - n0:j].max(), L[j - n0:j].min()
            bt.append({"s": gs, "d": s, "c": ch, "t": int(T[j]), "e": round(e / sc, 10), "sl": round((e - s * risk) / sc, 10), "pt": round((e + s * risk) / sc, 10), "lv": round((O[j + 1] - s * LIM * atr[j]) / sc, 10), "f": int(T[f - 1]),
                       "x": int(T[j + k]), "xp": round(float(ex) / sc, 10), "r": round(float(R[i]), 3), "k": KN[kind], "fk": FAIL_K,
                       "hh": round(hh / sc, 10), "ll": round(ll / sc, 10), "n": n0, "t0": int(T[j - n0] - tfh * 3600)})
json.dump(OUT, open("rbx_research_v667.json", "w"), separators=(",", ":"))
json.dump(bt, open("rbx_bt_v667.json", "w"), separators=(",", ":"))
from collections import Counter
print(len(bt), Counter(x["k"] for x in bt))
