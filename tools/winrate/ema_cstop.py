"""EMA: the stop on a candle's close on the honest pool"""
"""EMA v11 (v0.99.699): the honest pool — the touches of an hour in the order the bot gets them (the nearer level to
the hour's open first; the list had them by the model's score — a look-ahead: +0.88R -> +0.55R, ema_order.py). Was: EMA v10 (v0.99.671, more trades): the v9 rule with the top 4% of the scores instead of 3% (the walk-forward threshold
of each year at q 0.96; the deployed model's own thr at q 0.96 = 0.314072 by ema_thr.py). 2022-26 306 trades instead of 234
(+31%), the growth at an equal drawdown the same (x396k vs x283k), ~0.1R a trade less (more_trades.py emx)."""
import json, numpy as np, pandas as pd
import ema_h as E
from mk import ts
from bt_trades import gate_sym
d = E.d
SIDES, MAX_E200, MARGIN4H, STOP, TAKE, HOLD, PA, PF, DEEP = (1,), 10.0, 0.1, 0.75, 4.0, 72, 1.0, 0.33, 0.2
def sim(O, H, L, C, j, side, fill, datr):
    n = len(C); risk = fill * STOP * datr / 100
    stop = fill - side * risk; tp = fill + side * TAKE * risk; pt = fill + side * PA * risk; took = False
    e = min(n, j + HOLD); k = e - 1 - j; ex = C[e - 1]; kind = "time"
    for q in range(e - j):
        b = j + q
        if (side > 0 and L[b] <= stop) or (side < 0 and H[b] >= stop):
            gap = (side > 0 and O[b] <= stop) or (side < 0 and O[b] >= stop)
            ex = O[b] if (gap and q > 0) else stop; k = q; kind = "be" if took else "stop"; break
        if q > 0 and not took and ((side > 0 and H[b] >= pt) or (side < 0 and L[b] <= pt)):
            took = True; stop = fill
        if q > 0 and ((side > 0 and H[b] >= tp) or (side < 0 and L[b] <= tp)):
            ex = tp; k = q; kind = "take"; break
    fee = (0.001 + 0.0003 * (k + 1) / 24) * fill / risk
    rest = side * (ex - fill) / risk
    return ((PF * PA + (1 - PF) * rest) if took else rest) - fee, k + 1, kind, ex, took
side, tf, e200 = d.side.values, d.tf_s.values, d.s_d_ema200.values
thr = np.array([E.THR[y][0.97] if y in E.THR else np.inf for y in E.YR]); rel = E.SC - thr
bema = pd.read_parquet(f"{E.D}/er_all.parquet", columns=["s_b_ema50"]).s_b_ema50.values
LS_MIN = 0.00314
import mfeat
LS = mfeat.at(d.sym.values, E.T - 3600)[:, mfeat.NAMES.index('ls_d24')] * side
mask = np.isin(side, SIDES) & (e200 < MAX_E200) & (tf != "4h") & (bema > 0) & ~(LS < LS_MIN)
for Y in (2022, 2023, 2024, 2025):
    sc_ = E.S[str(Y)]; ref_ = (E.T >= ts(Y - 1)) & (E.T < ts(Y) - 21 * 86400); E.THR[Y][0.96] = float(np.quantile(sc_[ref_], 0.96))
idx = E.cand(0.96, mask)
idx = idx[d.pen.values[idx] >= 0.1 + DEEP * d.datr.values[idx]]
FILL = lambda i: float(d.lv.values[i]) * (1 - int(side[i]) * DEEP * float(d.datr.values[i]) / 100)
R = np.full(len(d), np.nan); K = np.zeros(len(d), np.int64); INFO = {}
for i in idx:
    O, H, L, C = E.bars(d.sym.values[i])
    r, k, kind, ex, took = sim(O, H, L, C, int(d.j.values[i]), int(side[i]), FILL(i), float(d.datr.values[i]))
    R[i], K[i] = r, k; INFO[i] = (kind, ex, took)
OPEN = np.full(len(d), np.nan)
by = {}
for i in idx: by.setdefault(d.sym.values[i], []).append(i)
for sym_, lst in by.items():
    O_, H_, L_, C_ = E.bars(sym_)
    for i in lst:
        j = int(d.j.values[i]); OPEN[i] = O_[j] if j < len(O_) else np.nan
NEAR = side * (OPEN - np.array([FILL(i) if i in INFO else np.nan for i in range(len(d))])) / (d.lv.values * d.datr.values / 100)
def rep_near(cap=12):
    o = idx[np.lexsort((NEAR[idx], E.T[idx]))]
    busy, act, out_ = {}, [], []
    for i in o:
        t = E.T[i]; k_ = (d.sym.values[i], side[i])
        if busy.get(k_, 0) > t or R[i] != R[i]: continue
        act = [a_ for a_ in act if a_[0] > t]
        if sum(1 for a_ in act if a_[1] == side[i]) >= cap: continue
        end = t + K[i] * 3600; busy[k_] = end; act.append((end, side[i])); out_.append(i)
    return np.array(out_, dtype=np.int64)

# ---- ema_cstop: the soft stop (0.75 dATR, the size) by a candle's close, the hard stop further by a touch; the partial
# 1/3 at +1R -> the stop (both) to the entry; take 4R; 72 h. The honest pool (the bot's touch order) re-selected
from common import load as _load
from numba import njit
@njit
def sim_cs(O, H, L, C, Tb, j, side, fill, datr, hard_a, kh):
    n = len(C); risk = fill * STOP * datr / 100
    ssl = fill - side * risk; hsl = fill - side * hard_a * datr / 100 * fill; tp = fill + side * TAKE * risk; pt = fill + side * PA * risk; took = False
    e = min(n, j + HOLD); k = e - 1 - j; ex = C[e - 1]; kind = 3
    for q in range(e - j):
        b = j + q
        if (side > 0 and L[b] <= hsl) or (side < 0 and H[b] >= hsl):
            gap = (side > 0 and O[b] <= hsl) or (side < 0 and O[b] >= hsl)
            ex = O[b] if (gap and q > 0) else hsl; k = q; kind = 0; break
        if q > 0 and not took and ((side > 0 and H[b] >= pt) or (side < 0 and L[b] <= pt)):
            took = True; hsl = fill; ssl = fill
        if q > 0 and ((side > 0 and H[b] >= tp) or (side < 0 and L[b] <= tp)):
            ex = tp; k = q; kind = 1; break
        if not took and kh > 0 and (Tb[b] + 3600) % (kh * 3600) == 0 and ((side > 0 and C[b] <= ssl) or (side < 0 and C[b] >= ssl)):
            ex = C[b]; k = q; kind = 4; break
    fee = (0.001 + 0.0003 * (k + 1) / 24) * fill / risk
    rest = side * (ex - fill) / risk
    return ((PF * PA + (1 - PF) * rest) if took else rest) - fee, k + 1, kind
TB = {}
def tb(sym):
    if sym not in TB:
        TB.clear(); TB[sym] = np.array([c["time"] for c in _load(sym)], np.int64)
    return TB[sym]
def run(nm, hard_a, kh):
    global R, K
    R0, K0 = R.copy(), K.copy(); KD = np.zeros(len(d), np.int64)
    for sym_ in sorted(set(d.sym.values[idx])):
        O_, H_, L_, C_ = E.bars(sym_); Tb = tb(sym_)
        for i in idx[d.sym.values[idx] == sym_]:
            if i not in INFO: continue
            r_, k_, kd = sim_cs(O_, H_, L_, C_, Tb, int(d.j.values[i]), int(side[i]), FILL(i), float(d.datr.values[i]), hard_a, kh)
            R[i], K[i], KD[i] = r_, k_, kd
    sel = rep_near(); r = R[sel]; y = E.YR[sel]
    ys = " ".join(f"{Y % 100}:{r[y == Y].mean():+.2f}" for Y in range(2022, 2026))
    print(f"{nm:34s} сделок {len(sel):4d} {r.mean():+.3f}R WR {np.mean(r > 0)*100:.0f}% стоп-закр {np.mean(KD[sel] == 4)*100:.0f}% авар {np.mean(KD[sel] == 0)*100:.0f}% | {ys}", flush=True)
    np.save(f"ema_cs_{hard_a}_{kh}.npy", np.c_[E.T[sel], E.T[sel] + K[sel] * 3600, R[sel], STOP * d.datr.values[sel] / 100, hard_a * d.datr.values[sel] / 100])
    json.dump([d.sym.values[i] for i in sel], open(f"ema_cs_{hard_a}_{kh}.json", "w"))
    R, K = R0, K0
run("касанием 0.75 dATR (сейчас)", STOP, 0)
for kh in (1, 4, 24):
    for hard in (1.0, 1.5):
        run(f"закр. {kh}ч за 0.75, авар. {hard}", hard, kh)
