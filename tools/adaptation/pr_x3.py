from pr_x_eval import run
for q in ("99", "95"):
    print(f"\n=== P/R q{q}")
    run("сейчас (по рынку)", "prv_lab_cs", q)
    for nm, fn in (("лимитка −0.2 ATR, 3ч", "px_lim2_3"), ("лимитка −0.3 ATR, 1ч", "px_lim3_1"), ("лимитка −0.3 ATR, 2ч", "px_lim3_2"),
                   ("лимитка −0.3 ATR, 3ч", "px_lim3_3"), ("лимитка −0.3 ATR, 6ч", "px_lim3_6"), ("лимитка −0.4 ATR, 3ч", "px_lim4_3")):
        run(nm, fn, q)
