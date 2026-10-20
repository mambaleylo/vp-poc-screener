import sys, numpy as np, pandas as pd
ARGS = sys.argv[1:]
import ema_h as E
d = E.d
q = float(ARGS[0])
target = 0.45 if q >= 0.97 else 0.50
grid = (0.0025, 0.005, 0.0075, 0.01, 0.0125, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10) if q >= 0.97 else (0.001, 0.002, 0.003, 0.004, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.03)
side, tf, e200, n = d.side.values, d.tf_s.values, d.s_d_ema200.values, d.n_i.values
bema = pd.read_parquet(f"{E.D}/er_all.parquet", columns=["s_b_ema50"]).s_b_ema50.values
thr = np.array([E.THR[y][q] if y in E.THR else np.inf for y in E.YR]); rel = E.SC - thr
NOW = (side > 0) & (e200 < 10) & ((tf != "4h") | (rel >= 0.1)) & (bema > 0)
def run(nm, mask, **kw):
    kw.setdefault("take", 3.0)
    idx = E.cand(q, mask); R, K, KD = E.outcomes(idx, **kw); tr = E.replay(idx, R, K)
    E.line(nm, tr, R, K, KD, target, grid)
print(f"== q {q}: поверх v0.99.645")
run("сейчас (v0.99.645)", NOW)
run("без EMA 20 (4ч)", NOW & (n != 20))
run("без 4ч совсем", NOW & (tf != "4h"))
run("4ч с запасом 0.2", (side > 0) & (e200 < 10) & ((tf != "4h") | (rel >= 0.2)) & (bema > 0))
run("день тоже с запасом 0.05", NOW & ((tf != "1d") | (rel >= 0.05)))
run("EMA200 < 7", NOW & (e200 < 7))
run("BTC выше EMA50 больше чем на 2%", NOW & (bema > 2))
run("держать 96ч", NOW, hold=96)
run("тейк 3.5R", NOW, take=3.5)
