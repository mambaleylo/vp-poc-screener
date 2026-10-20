import os; os.environ["CAS_SEL"] = "cas_sel_base3.npz"
from cas_wr import trades
from wr_eval import stats
from mk import ts
for q, tg, nm_ in ((0.995, 0.45, "бот"), (0.98, 0.50, "проверка")):
    print(f"\n=== каскад (3 модели), {nm_}")
    for nm, kw in (("сейчас: 2R, до 12", {}), ("2.5R, до 8", dict(take_r=2.5, cap=8)), ("2.5R, треть на +0.7R, до 6", dict(take_r=2.5, cap=6, part_r=0.7, part_f=0.33)),
                   ("2.5R, треть на +0.7R, до 8", dict(take_r=2.5, cap=8, part_r=0.7, part_f=0.33)), ("2.5R, треть на +1R, до 6", dict(take_r=2.5, cap=6, part_r=1.0, part_f=0.33)),
                   ("2.5R, треть на +1R, до 4", dict(take_r=2.5, cap=4, part_r=1.0, part_f=0.33)), ("2.5R, четверть на +0.7R, до 6", dict(take_r=2.5, cap=6, part_r=0.7, part_f=0.25))):
        stats(nm, trades(q, **kw), ts(2022), tg)
