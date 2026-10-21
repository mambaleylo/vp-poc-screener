"""EMA v10 (v0.99.671, more trades): the v9 rule with the top 4% of the scores instead of 3% (the walk-forward threshold
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
tr = E.replay(idx, R, K)
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
                "sl": round((fill - s * risk) / sc, 10), "tp": round((fill + s * TAKE * risk) / sc, 10), "pt": round((fill + s * PA * risk) / sc, 10),
                "x": int(E.T[i] + K[i] * 3600), "xp": round(float(ex) / sc, 10), "r": round(float(R[i]), 3), "k": kind, "part": bool(took)})
json.dump(out, open("emx_bt_v671.json", "w"), separators=(",", ":"))
m = json.load(open("vp_ema_model_v9.json"))
m.update({"ver": 10, "q": 0.96, "thr": 0.314072, "tfs": ["1d", "1w", "1M"], "ls_min_d24": LS_MIN, "rule": {"stop_datr": STOP, "take_r": TAKE, "hold_h": HOLD, "part_r": PA, "part_f": PF, "deep_datr": DEEP}})
m["research"]["years"] = years; m["research"]["max_losing_streak"] = mx
m["research"]["filters"] = "лонги при BTC выше EMA50 дня, цена < 10 дн. ATR над EMA200 дня, без касаний на 4ч; не входит, если толпа за сутки не прибавила в лонгах; 1/3 на +1R → безубыток, тейк 4R; вход лимиткой на 0.2 дн. ATR за EMA"
json.dump(m, open("vp_ema_model_v10.json", "w"), separators=(",", ":"))
r = R[tr]
from collections import Counter
print("trades", len(out), "avg", round(float(r.mean()), 3), "wr", round(float((r > 0).mean()) * 100, 1), "streak", mx, Counter(t["k"] for t in out))
