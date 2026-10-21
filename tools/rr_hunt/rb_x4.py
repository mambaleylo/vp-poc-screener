"""📈 breakout round 4: the charts apart (day / 12h / both) and per side, on the v0.99.663 rule"""
import rb_h as B
from rb_x2 import run
from wr_eval import stats
for nm_, M, tg in (("бот", B.BOT, 0.45), ("проверка", B.CHECK, 0.50)):
    print(f"\n=== пробой, {nm_}", flush=True)
    for nm, m in (("оба графика (v663)", M), ("только день", M & (B.TF == 24)), ("только 12ч", M & (B.TF == 12)),
                  ("только лонги", M & (B.SD > 0)), ("только шорты", M & (B.SD < 0))):
        stats(nm, run(m), B.START, tg)
