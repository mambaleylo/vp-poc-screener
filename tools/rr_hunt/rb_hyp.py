import sys, numpy as np
ARGS = sys.argv[1:]
import rb_h as B
which = ARGS[0]; part = ARGS[1]
M = B.BOT if which == "bot" else B.CHECK
target = 0.45
def run(nm, mask=None, stop=1.5, ex="dc20"):
    R, H = B.lab(stop, ex)
    tr = B.replay(M if mask is None else (M & mask), R, H)
    B.line(nm, tr, R, H, target)
print(f"== {which}: сделок, в неделю, ср.R, WR, убыточных подряд | 2021..2025-26 | риск и рост при просадке 1 из 10 = 45%")
if part == "exits":
    run("сейчас: стоп 1.5, выход dc20")
    for ex in ("t2", "t3", "t5", "t8", "ch5", "dc10", "dc50", "be1dc20", "be1dc50", "half2dc20"):
        run(f"выход {ex}", ex=ex)
    for st in (1.0, 2.0):
        run(f"стоп {st}, dc20", stop=st)
if part == "filters":
    run("сейчас")
    ar, vz, bk = B.F["atr_ratio"], B.F["vol_z"], B.BRK
    for nm, m in (("ATR ratio > 0.8", ar > 0.8), ("ATR ratio > 0.9", ar > 0.9), ("объём vol_z > 0", vz > 0), ("объём vol_z > 0.5", vz > 0.5),
                  ("пробой > 0.2 ATR", bk > 0.2), ("пробой > 0.4 ATR", bk > 0.4), ("BTC за 24ч по стороне > -4%", B.SD * B.F["b_r24"] > -4),
                  ("BTC vs EMA50 по стороне > 0", B.SD * B.F["b_e50"] > 0), ("только лонги", B.SD > 0), ("только шорты", B.SD < 0),
                  ("только день", B.TF == 24), ("только 12ч", B.TF == 12)):
        run(nm, m)
