import sys, numpy as np
ARGS = sys.argv[1:]
import ema_h as E
d = E.d
q = float(ARGS[0])
target = 0.45 if q >= 0.97 else 0.50
grid = (0.0025, 0.005, 0.0075, 0.01, 0.0125, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10) if q >= 0.97 else (0.001, 0.002, 0.003, 0.004, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.03)
side, tf, e200, pen = d.side.values, d.tf_s.values, d.s_d_ema200.values, d.pen.values
thr = np.array([E.THR[y][q] if y in E.THR else np.inf for y in E.YR]); rel = E.SC - thr
best = (e200 < 10) & (side > 0) & ((tf != "4h") | (rel >= 0.1))
LV = d.lv.values.copy()
def run(nm, mask=None, deep=0.0, **kw):
    d["lv"] = LV * (1 - side * deep / 100)
    m = mask & (pen >= max(0.1, deep)) if deep else mask
    idx = E.cand(q, m); R, K, KD = E.outcomes(idx, **kw); tr = E.replay(idx, R, K)
    E.line(nm, tr, R, K, KD, target, grid)
    d["lv"] = LV
print(f"== q {q}: лучшая комбинация (EMA200<10 дн.ATR + лонги + 4ч с запасом 0.1 + тейк 3R) и её варианты")
run("лучшая", best, take=3.0)
for dp in (0.3, 0.6):
    run(f"лучшая + лимит глубже на {dp}%", best, deep=dp, take=3.0)
run("лучшая + стоп по закр. 1ч / авар. 1.0", best, take=3.0, close_tf=1, hard=1.0)
run("лучшая + стоп 0.6 касанием", best, take=3.0, a=0.6)
run("лучшая + стоп 0.9 касанием", best, take=3.0, a=0.9)
