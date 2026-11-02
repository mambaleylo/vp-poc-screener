"""EMA v13 (v0.99.769, the improvement round — tools/ema_model ema_var.py + tools/winrate money_ema.py): v12 with
1) the backtest at ANY touch of the limit (the lab had wanted the touch hour 0.1% past it, but the bot trades every touch —
   live and at the hour's settle; the list was a subset of the bot's trades: 311 -> 343, +0.75R -> +0.77R),
2) no crowd filter (ls_min_d24 off: 442 trades +0.66R; the bundle's money +35% the usual year, +45% the last 12 months at
   the same drawdown, better in 6 of 6 paired noise runs on both),
3) the candles with the days Binance's monthly archives had cut (tools/zones_model fill_gaps.py), the scores re-made,
4) the research's years 2025 and 2026 apart (the user: the 2025 model scores both, but they are different years).
The model's trees and thr are the deployed ones (only the filter and the research numbers change; ver stays 12).
usage: python3 ema_export13.py   (from tools/ema_model)"""
import json, datetime as dt, numpy as np, pandas as pd
import ema_h as E
from mk import ts
def gate_sym(sym):   # = tools/adaptation/bt_trades.py
    b = sym[:-4]
    return (b[4:] if b.startswith("1000") else b) + "_USDT", (1000.0 if b.startswith("1000") else 1.0)
d = E.d
SIDES, MAX_E200, MARGIN4H, STOP, TAKE, HOLD, PA, PF, DEEP = (1,), 10.0, 0.1, 0.75, 4.0, 72, 1.0, 0.33, 0.2
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
mask = np.isin(side, SIDES) & (e200 < MAX_E200) & (tf != "4h") & (bema > 0)
for Y in (2022, 2023, 2024, 2025):
    sc_ = E.S[str(Y)]; ref_ = (E.T >= ts(Y - 1)) & (E.T < ts(Y) - 21 * 86400); E.THR[Y][0.96] = float(np.quantile(sc_[ref_], 0.96))
thr96 = np.array([E.THR[y][0.96] if y in E.THR else np.inf for y in E.YR])
idx = np.where((E.YR >= 2022) & (E.SC >= thr96) & mask)[0]
idx = idx[d.pen.values[idx] >= DEEP * d.datr.values[idx]]   # v13: any touch of the limit (the bot's), no 0.1% margin
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
YT = np.array([dt.datetime.fromtimestamp(int(t), dt.timezone.utc).year for t in E.T[tr]])   # the calendar year (E.YR caps it at 2025)
for Y in (2022, 2023, 2024, 2025, 2026):
    m = YT == Y; rs = R[tr[m]]
    o = tr[m][np.argsort(E.T[tr[m]] + K[tr[m]] * 3600)]; c = np.cumsum(R[o])
    dd = float(np.max(np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c]))
    wk = ((ts(Y + 1) if Y < 2026 else ts(2026, 10)) - ts(Y)) / 604800
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
bt = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json")); bt["emx"] = out
json.dump(bt, open("/home/user/vp-poc-screener/vp_bt_trades.json", "w"), separators=(",", ":"))
m = json.load(open("/home/user/vp-poc-screener/vp_ema_model.json"))   # the deployed v12: the trees and thr unchanged
m.pop("ls_min_d24", None)
m["research"]["years"] = years; m["research"]["max_losing_streak"] = mx; m["research"]["q"] = 0.96
m["research"]["filters"] = "лонги при BTC выше EMA50 дня, цена < 10 дн. ATR над EMA200 дня, без касаний на 4ч; 1/3 на +1R → безубыток, тейк 4R; вход лимиткой на 0.2 дн. ATR за EMA"
json.dump(m, open("/home/user/vp-poc-screener/vp_ema_model.json", "w"), separators=(",", ":"))
r = R[tr]
from collections import Counter
print("trades", len(out), "avg", round(float(r.mean()), 3), "wr", round(float((r > 0).mean()) * 100, 1), "streak", mx, Counter(t["k"] for t in out))
