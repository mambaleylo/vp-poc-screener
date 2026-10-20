from pr_x_eval import run
import numpy as np, pr_hyp as P
for q in ("99", "95"):
    print(f"\n=== P/R q{q}")
    run("сейчас (по рынку)", "prv_lab_cs", q)
    for nm, fn in (("лимитка −0.3 ATR, ждать 3ч", "px_lim3_3"), ("лимитка −0.5 ATR, 3ч", "px_lim5_3"), ("лимитка −0.5 ATR, 6ч", "px_lim5_6"), ("лимитка −1 ATR, 6ч", "px_lim10_6")):
        run(nm, fn, q)
