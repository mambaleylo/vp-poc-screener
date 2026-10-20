import sys
WHICH = sys.argv[1]
from wr_eval import stats
from mk import ts
if WHICH == "cas":
    from cas_wr import trades
    for q, tg, nm_ in ((0.995, 0.45, "бот"), (0.98, 0.50, "проверка")):
        print(f"\n=== каскад, {nm_}")
        for tk in (2.5, 3.0):
            for (pr, pf, pn) in ((0.0, 0.5, "без частичной"), (1.0, 0.33, "треть на +1R"), (0.7, 0.33, "треть на +0.7R"), (0.7, 0.5, "половина на +0.7R"), (1.0, 0.5, "половина на +1R")):
                for cap in (4, 6, 8):
                    stats(f"тейк {tk}R, {pn}, до {cap}", trades(q, take_r=tk, cap=cap, part_r=pr, part_f=pf), ts(2022), tg)
else:
    import rb_h as B
    from rb_wr import run
    for nm_, M, tg in (("бот", B.BOT, 0.45), ("проверка", B.CHECK, 0.50)):
        print(f"\n=== пробой, {nm_}")
        for (pr, pf, pn) in ((0.0, 0.5, "сейчас"), (1.0, 0.33, "треть на +1R"), (1.0, 0.25, "четверть на +1R"), (0.75, 0.33, "треть на +0.75R"), (1.0, 0.5, "половина на +1R"), (1.5, 0.33, "треть на +1.5R")):
            for cap in (4, 5, 6):
                stats(f"{pn}, до {cap}", run(M, cap=cap, part_r=pr, part_f=pf), B.START, tg)
