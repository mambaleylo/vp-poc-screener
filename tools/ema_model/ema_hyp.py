import sys, numpy as np
ARGS = sys.argv[1:]
import ema_h as E
d = E.d
q = float(ARGS[0]); part = ARGS[1]
target = 0.45 if q >= 0.97 else 0.50
grid = (0.0025, 0.005, 0.0075, 0.01, 0.0125, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10) if q >= 0.97 else (0.001, 0.002, 0.003, 0.004, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.03)
side, tf, e200 = d.side.values, d.tf_s.values, d.s_d_ema200.values
def run(nm, mask=None, **kw):
    idx = E.cand(q, mask); R, K, KD = E.outcomes(idx, **kw); tr = E.replay(idx, R, K)
    E.line(nm, tr, R, K, KD, target, grid)
print(f"== q {q}: сделок, в неделю, ср.R (от риска позиции), WR, стопов, убыточных подряд | 2022..2025-26 | риск и рост при просадке 1 из 10 = {target:.0%}")
if part == "filters":
    run("сейчас")
    run("только лонги", side > 0)
    run("без 4ч", tf != "4h")
    run("только 4ч", tf == "4h")
    run("цена от EMA200 дня < +10% (по стороне)", e200 < 10)
    run("лонги + без 4ч", (side > 0) & (tf != "4h"))
    run("лонги + EMA200 < 10%", (side > 0) & (e200 < 10))
    run("лонги + без 4ч + EMA200 < 10%", (side > 0) & (tf != "4h") & (e200 < 10))
if part == "exits":
    run("сейчас: стоп 0.75 касанием, тейк 4R, 72ч")
    for ct, hd in ((1, 1.5), (1, 2.0), (4, 1.5), (4, 2.0)):
        run(f"стоп 0.75 по закрытию {ct}ч, авар. {hd}", close_tf=ct, hard=hd)
    for a in (0.5, 1.0, 1.5):
        run(f"стоп {a} касанием", a=a)
    for tk in (2.0, 3.0, 6.0, 0.0):
        run(f"тейк {tk or 'нет'}R", take=tk)
    for h in (48, 120):
        run(f"держать {h}ч", hold=h)
    for be in (1.0, 2.0):
        run(f"безубыток после +{be}R", be=be)
