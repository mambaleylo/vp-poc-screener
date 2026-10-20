"""EMA, round 2 on top of the deployed rule (longs, EMA200 < 10 daily ATR, 4h margin 0.1, take 3R, stop 0.75, 72 h):
a confirmed entry (the touch hour closes back above the EMA, entry at that close), the BTC trend, an hourly entry cap."""
import sys, numpy as np, pandas as pd
from numba import njit
ARGS = sys.argv[1:]
import ema_h as E
d = E.d
q = float(ARGS[0])
target = 0.45 if q >= 0.97 else 0.50
grid = (0.0025, 0.005, 0.0075, 0.01, 0.0125, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10) if q >= 0.97 else (0.001, 0.002, 0.003, 0.004, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.03)
side, tf, e200 = d.side.values, d.tf_s.values, d.s_d_ema200.values
bema = pd.read_parquet(f"{E.D}/er_all.parquet", columns=["s_b_ema50", "s_b7d"])
thr = np.array([E.THR[y][q] if y in E.THR else np.inf for y in E.YR]); rel = E.SC - thr
BEST = (side > 0) & (e200 < 10) & ((tf != "4h") | (rel >= 0.1))
@njit(cache=True)
def simx(O, H, L, C, j0, fill, stop, tp, hold, risk):
    """long from bar j0 (entered at fill): stop first, take not in the entry bar; R per risk"""
    e = min(len(C), j0 + hold); k = e - 1 - j0; ex = C[e - 1]; kind = 3
    for q in range(e - j0):
        b = j0 + q
        if L[b] <= stop:
            ex = O[b] if (O[b] <= stop and q > 0) else stop; k = q; kind = 0; break
        if q > 0 and H[b] >= tp:
            ex = tp; k = q; kind = 2; break
    return (ex - fill - (0.001 + 0.0003 * (k + 1) / 24) * fill) / risk, k + 1, kind
def confirmed(idx, same_tp):
    """wait for the touch hour's close: in only if it closed back above the EMA and the stop was not hit"""
    R = np.full(len(d), np.nan); K = np.zeros(len(d), np.int64); KD = np.full(len(d), -1)
    for i in idx:
        O, H, L, C = E.bars(d.sym.values[i]); j = int(d.j.values[i]); lv = float(d.lv.values[i])
        r0 = lv * 0.75 * float(d.datr.values[i]) / 100; stop = lv - r0
        if L[j] <= stop or C[j] <= lv: continue
        fill = C[j]; risk = fill - stop
        tp = lv + 3 * r0 if same_tp else fill + 3 * risk
        r, k, kd = simx(O, H, L, C, j + 1, fill, stop, tp, 71, risk)
        R[i], K[i], KD[i] = r, k + 1, kd
    return R, K, KD
def run(nm, mask, R=None, cap=12, per_hour=None):
    idx = E.cand(q, mask)
    if R is None: R, K, KD = E.outcomes(idx, take=3.0)
    else: R, K, KD = R(idx)
    if per_hour:
        o = idx[np.lexsort((-E.SC[idx], E.T[idx]))]; keep, cnt = [], {}
        for i in o:
            if R[i] != R[i]: continue
            c = cnt.get(E.T[i], 0)
            if c < per_hour: keep.append(i); cnt[E.T[i]] = c + 1
        idx = np.array(keep, dtype=np.int64)
    tr = E.replay(idx, R, K, cap=cap)
    E.line(nm, tr, R, K, KD, target, grid)
print(f"== q {q}: поверх внедрённого правила")
run("внедрено (v0.99.644)", BEST)
run("вход по закрытию часа над EMA, тейк на месте", BEST, R=lambda i: confirmed(i, True))
run("вход по закрытию часа над EMA, тейк 3R от нового риска", BEST, R=lambda i: confirmed(i, False))
run("+ BTC выше своей EMA50 дня", BEST & (bema.s_b_ema50.values > 0))
run("+ BTC за неделю не упал > 10%", BEST & (bema.s_b7d.values > -10))
for ph in (2, 4):
    run(f"+ не больше {ph} входов в час", BEST, per_hour=ph)
for cap in (6, 20):
    run(f"+ максимум {cap} открытых", BEST, cap=cap)
