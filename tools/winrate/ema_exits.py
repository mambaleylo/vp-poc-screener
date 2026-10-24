"""EMA v0.99.707: the v0.99.700 list with the bot's reach filter (|px - EMA| <= 1.5 dATR at the hour's start, emx_levels): 6% of the touches were spikes to an EMA the bot does not arm. """
"""EMA v12 (v0.99.700): v11 + the stop at a 4h close (0.75 dATR), the emergency stop 1.5 dATR. EMA v11 (v0.99.699): the honest pool — the touches of an hour in the order the bot gets them (the nearer level to
the hour's open first; the list had them by the model's score — a look-ahead: +0.88R -> +0.55R, ema_order.py). Was: EMA v10 (v0.99.671, more trades): the v9 rule with the top 4% of the scores instead of 3% (the walk-forward threshold
of each year at q 0.96; the deployed model's own thr at q 0.96 = 0.314072 by ema_thr.py). 2022-26 306 trades instead of 234
(+31%), the growth at an equal drawdown the same (x396k vs x283k), ~0.1R a trade less (more_trades.py emx)."""
import json, numpy as np, pandas as pd
import ema_h as E
from mk import ts
from bt_trades import gate_sym
d = E.d
import os
SIDES, MAX_E200, MARGIN4H, STOP, TAKE, HOLD, PA, PF, DEEP = (1,), 10.0, 0.1, 0.75, float(os.environ.get("ETK", 4.0)), int(os.environ.get("EHD", 72)), 1.0, 0.33, 0.2
HARD_X, KH = 2.0, 4   # v0.99.700: the stop at a 4h close beyond 0.75 dATR, the emergency one at 1.5 dATR (ema_cstop.py)
from common import load as _load
_TB = {}
def _tb(sym):
    if sym not in _TB:
        _TB.clear(); _TB[sym] = np.array([c["time"] for c in _load(sym)], np.int64)
    return _TB[sym]
CUR = {"sym": None}
def sim(O, H, L, C, j, side, fill, datr):
    Tb = _tb(CUR["sym"])
    n = len(C); risk = fill * STOP * datr / 100
    ssl = fill - side * risk; hsl = fill - side * HARD_X * risk; tp = fill + side * TAKE * risk; pt = fill + side * PA * risk; took = False
    e = min(n, j + HOLD); k = e - 1 - j; ex = C[e - 1]; kind = "time"
    for q in range(e - j):
        b = j + q
        if (side > 0 and L[b] <= hsl) or (side < 0 and H[b] >= hsl):
            gap = (side > 0 and O[b] <= hsl) or (side < 0 and O[b] >= hsl)
            ex = O[b] if (gap and q > 0) else hsl; k = q; kind = "be" if took else "hard"; break
        if q > 0 and not took and ((side > 0 and H[b] >= pt) or (side < 0 and L[b] <= pt)):
            took = True; hsl = fill
        if q > 0 and ((side > 0 and H[b] >= tp) or (side < 0 and L[b] <= tp)):
            ex = tp; k = q; kind = "take"; break
        if not took and (Tb[b] + 3600) % (KH * 3600) == 0 and ((side > 0 and C[b] <= ssl) or (side < 0 and C[b] >= ssl)):
            ex = C[b]; k = q; kind = "stop"; break
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
PXH = np.full(len(d), np.nan); by0 = {}
for i in idx: by0.setdefault(d.sym.values[i], []).append(i)
for sym_, lst in by0.items():
    O_, H_, L_, C_ = E.bars(sym_)
    for i in lst:
        j = int(d.j.values[i]); PXH[i] = C_[j - 1] if j >= 1 else np.nan
reach = np.abs(PXH[idx] - d.lv.values[idx]) / PXH[idx] * 100 <= 1.5 * d.datr.values[idx]
print("в досягаемости", round(float(reach.mean()) * 100, 1), "%", flush=True)
idx = idx[reach]
FILL = lambda i: float(d.lv.values[i]) * (1 - int(side[i]) * DEEP * float(d.datr.values[i]) / 100)
R = np.full(len(d), np.nan); K = np.zeros(len(d), np.int64); INFO = {}
for i in idx:
    O, H, L, C = E.bars(d.sym.values[i]); CUR["sym"] = d.sym.values[i]
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
tr = rep_near()
years = {}
for Y in (2022, 2023, 2024, 2025):
    m = E.YR[tr] == Y; rs = R[tr[m]]
    o = tr[m][np.argsort(E.T[tr[m]] + K[tr[m]] * 3600)]; c = np.cumsum(R[o])
    dd = float(np.max(np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c]))
    wk = ((ts(Y + 1) if Y < 2025 else ts(2026, 10)) - ts(Y)) / 604800
    years[str(Y)] = {"n": int(m.sum()), "avg": round(float(rs.mean()), 3), "wk": round(float(m.sum() / wk), 1), "sum": round(float(rs.sum()), 1),
                     "dd": round(dd, 1), "wr": round(float((rs > 0).mean() * 100), 1)}
    print(Y, years[str(Y)], flush=True)
o_all = tr[np.argsort(E.T[tr] + K[tr] * 3600)]; run = mx = 0
for i in o_all: run = run + 1 if R[i] < 0 else 0; mx = max(mx, run)
out = []
for i in tr:
    kind, ex, took = INFO[i]; s = int(side[i]); fill = FILL(i)
    risk = fill * STOP * float(d.datr.values[i]) / 100
    gs, sc = gate_sym(d.sym.values[i])
    out.append({"s": gs, "d": s, "c": "1h", "tf": str(tf[i]), "n": int(d.n_i.values[i]), "t": int(E.T[i]), "e": round(fill / sc, 10), "ema": round(float(d.lv.values[i]) / sc, 10),
                "sl": round((fill - s * risk) / sc, 10), "hs": round((fill - s * HARD_X * risk) / sc, 10), "tp": round((fill + s * TAKE * risk) / sc, 10), "pt": round((fill + s * PA * risk) / sc, 10),
                "x": int(E.T[i] + K[i] * 3600), "xp": round(float(ex) / sc, 10), "r": round(float(R[i]), 3), "k": kind, "part": bool(took)})
json.dump(out, open(f"emx_bt_x_{TAKE}_{HOLD}.json", "w"), separators=(",", ":"))
np.save(f"emaqx_{TAKE}_{HOLD}.npy", np.c_[E.T[tr], E.T[tr] + K[tr] * 3600, R[tr], STOP * d.datr.values[tr] / 100, HARD_X * STOP * d.datr.values[tr] / 100]); json.dump([d.sym.values[i] for i in tr], open(f"emaqx_{TAKE}_{HOLD}.json", "w"))
m = json.load(open("/home/user/vp-poc-screener/vp_ema_model.json"))   # the deployed v10: only the research numbers change
m["research"]["years"] = years; m["research"]["max_losing_streak"] = mx
m["research"]["filters"] = "лонги при BTC выше EMA50 дня, цена < 10 дн. ATR над EMA200 дня, без касаний на 4ч; не входит, если толпа за сутки не прибавила в лонгах; 1/3 на +1R → безубыток, тейк 4R; вход лимиткой на 0.2 дн. ATR за EMA"
json.dump(m, open(f"vp_ema_model_x_{TAKE}_{HOLD}.json", "w"), separators=(",", ":"))
r = R[tr]
from collections import Counter
print("trades", len(out), "avg", round(float(r.mean()), 3), "wr", round(float((r > 0).mean()) * 100, 1), "streak", mx, Counter(t["k"] for t in out))
