"""EMA: the model retrained on longs only (er_wf_long.py) vs the deployed one, with the deployed rule (+ the BTC EMA50 filter)."""
import sys, numpy as np, pandas as pd
ARGS = sys.argv[1:]
import ema_h as E
from mk import ts
d = E.d
q = float(ARGS[0])
target = 0.45 if q >= 0.97 else 0.50
grid = (0.0025, 0.005, 0.0075, 0.01, 0.0125, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10) if q >= 0.97 else (0.001, 0.002, 0.003, 0.004, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.03)
side, tf, e200 = d.side.values, d.tf_s.values, d.s_d_ema200.values
bema = pd.read_parquet(f"{E.D}/er_all.parquet", columns=["s_b_ema50"]).s_b_ema50.values
SC0, THR0 = E.SC.copy(), {y: dict(v) for y, v in E.THR.items()}
def use(scfile):
    if scfile is None:
        E.SC[:] = SC0; E.THR.clear(); E.THR.update({y: dict(v) for y, v in THR0.items()}); return
    S = np.load(scfile); T = E.T
    for Y in (2022, 2023, 2024, 2025):
        sc = S[str(Y)]
        te = (T >= ts(Y)) & (T < (ts(Y + 1) if Y < 2025 else ts(2027)))
        E.SC[te] = sc[te]
        ref = (T >= ts(Y - 1)) & (T < ts(Y) - 21 * 86400) & (side > 0)
        E.THR[Y] = {qq: float(np.nanquantile(sc[ref], qq)) for qq in (0.80, 0.90, 0.95, 0.97, 0.98, 0.99)}
def run(nm, btc=False, take=3.0):
    thr = np.array([E.THR[y][q] if y in E.THR else np.inf for y in E.YR]); rel = E.SC - thr
    m = (side > 0) & (e200 < 10) & ((tf != "4h") | (rel >= 0.1))
    if btc: m &= bema > 0
    idx = E.cand(q, m); R, K, KD = E.outcomes(idx, take=take); tr = E.replay(idx, R, K)
    E.line(nm, tr, R, K, KD, target, grid)
print(f"== q {q} (порог — квантиль среди лонгов для новых моделей)")
use(None); run("внедрённая модель"); run("внедрённая + BTC>EMA50", btc=True)
for lab in ("F_0.75_4.0_3", "F_0.75_3.0_3"):
    use(f"{E.D}/er_sc_long_{lab}.npz")
    run(f"модель только на лонгах, метка {lab}"); run(f"... + BTC>EMA50", btc=True)
