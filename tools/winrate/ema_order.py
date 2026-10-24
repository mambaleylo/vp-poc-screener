"""audit of EMA like ⚡ / SMC: the pool's order inside an hour — the score (the list) vs the nearer level first (the bot)"""
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

# ---- ema_order: the hour's touches ordered by the score (the list) vs the level the price reaches first (the bot) ----
OPEN = np.full(len(d), np.nan)
by = {}
for i in idx: by.setdefault(d.sym.values[i], []).append(i)
for sym_, lst in by.items():
    O, H, L, C = E.bars(sym_)
    for i in lst:
        j = int(d.j.values[i]); OPEN[i] = O[j] if j < len(O) else np.nan
NEAR = side * (OPEN - np.array([FILL(i) if i in INFO else np.nan for i in range(len(d))])) / (d.lv.values * d.datr.values / 100)
def rep(key, cap=12):
    o = idx[np.lexsort((key[idx], E.T[idx]))]
    sym, sd = d.sym.values, side
    busy, act, out = {}, [], []
    for i in o:
        t = E.T[i]; k_ = (sym[i], sd[i])
        if busy.get(k_, 0) > t or R[i] != R[i]: continue
        act = [a_ for a_ in act if a_[0] > t]
        if sum(1 for a_ in act if a_[1] == sd[i]) >= cap: continue
        end = t + K[i] * 3600; busy[k_] = end; act.append((end, sd[i])); out.append(i)
    return np.array(out, dtype=np.int64)
def show(nm, sel):
    r = R[sel]; y = E.YR[sel]
    ys = " ".join(f"{Y % 100}:{r[y == Y].mean():+.2f}({(y == Y).sum()})" for Y in range(2022, 2026))
    print(f"{nm:34s} сделок {len(sel):4d} {r.mean():+.3f}R WR {np.mean(r > 0)*100:.0f}% сумма {r.sum():+.0f}R | {ys}", flush=True)
nh = {}
for i in idx: nh[(E.T[i], side[i])] = nh.get((E.T[i], side[i]), 0) + 1
print("кандидатов", len(idx), "· часов с > 1 касанием в сторону:", sum(1 for v in nh.values() if v > 1), "из", len(nh))
a = rep(-E.SC); b = rep(NEAR)
show("по баллу модели (как в списке)", a); show("ближний уровень первым (как бот)", b)
rng = np.random.default_rng(1)
for k_ in range(2): show(f"случайный порядок #{k_ + 1}", rep(rng.random(len(d))))
print("выбраны иначе:", len(set(a) ^ set(b)), "из", len(a))
np.savez("ema_order.npz", a=a, b=b)
def one_per(rank):
    best = {}
    for i in idx:
        k = (d.sym.values[i], side[i], E.T[i])
        if R[i] != R[i]: continue
        if k not in best or rank[i] < rank[best[k]]: best[k] = i
    return np.array(sorted(best.values()), dtype=np.int64)
print("== на монету в час — один уровень (решается в начале часа), дальше порядок бота")
for nm, rk in (("лучший по баллу", -E.SC), ("самый дальний", -NEAR), ("самый ближний", NEAR)):
    keep = one_per(rk); idx0 = idx; idx = keep
    show(nm, rep(NEAR)); idx = idx0
