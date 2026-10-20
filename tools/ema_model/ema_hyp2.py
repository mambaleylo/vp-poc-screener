import sys, numpy as np
ARGS = sys.argv[1:]
import ema_h as E
d = E.d
q = float(ARGS[0])
target = 0.45 if q >= 0.97 else 0.50
grid = (0.0025, 0.005, 0.0075, 0.01, 0.0125, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10) if q >= 0.97 else (0.001, 0.002, 0.003, 0.004, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.03)
side, tf, e200 = d.side.values, d.tf_s.values, d.s_d_ema200.values
thr = np.array([E.THR[y][q] if y in E.THR else np.inf for y in E.YR]); rel = E.SC - thr
def run(nm, mask=None, **kw):
    idx = E.cand(q, mask); R, K, KD = E.outcomes(idx, **kw); tr = E.replay(idx, R, K)
    E.line(nm, tr, R, K, KD, target, grid)
print(f"== q {q}")
f1 = e200 < 10
run("сейчас")
run("EMA200<10 + тейк 3R", f1, take=3.0)
run("EMA200<10 + тейк 3R + лонги", f1 & (side > 0), take=3.0)
for x in (0.05, 0.1):
    run(f"EMA200<10 + тейк 3R + 4ч только с запасом +{x}", f1 & ((tf != "4h") | (rel >= x)), take=3.0)
    run(f"... + лонги", f1 & (side > 0) & ((tf != "4h") | (rel >= x)), take=3.0)
run("EMA200<10 + тейк 3R + лонги + стоп по закр. 1ч/1.5", f1 & (side > 0), take=3.0, close_tf=1, hard=1.5)
run("EMA200<10 + тейк 3R + лонги + стоп по закр. 4ч/1.5", f1 & (side > 0), take=3.0, close_tf=4, hard=1.5)
for tk in (2.5, 3.5):
    run(f"EMA200<10 + лонги + тейк {tk}R", f1 & (side > 0), take=tk)
for h in (96, 120):
    run(f"EMA200<10 + лонги + тейк 3R + {h}ч", f1 & (side > 0), take=3.0, hold=h)
for lim in (5, 15):
    run(f"EMA200<{lim} + лонги + тейк 3R", (e200 < lim) & (side > 0), take=3.0)
