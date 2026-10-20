import numpy as np, rb_h as B
from rb_fail import run
from wr_eval import stats
def loss(tr):
    r = np.array([x[2] for x in tr]); l = r[r < 0]
    return f"   средний минус {l.mean():+.2f}R, полных стопов (≤ −0.9R) {np.mean(r <= -0.9)*100:.0f}% сделок"
for nm_, M, tg in (("бот", B.BOT, 0.45), ("проверка", B.CHECK, 0.50)):
    print(f"\n=== {nm_}")
    for nm, kw in (("сейчас", {}), ("возврат в коридор, 1 свеча", dict(fail_k=1)), ("возврат в коридор, 2 свечи", dict(fail_k=2)),
                   ("сильный ≥0.6 ATR", dict(min_brk=0.6)), ("сильный ≥0.45 ATR", dict(min_brk=0.45)),
                   ("сильный ≥0.6 + возврат 2", dict(min_brk=0.6, fail_k=2)), ("сильный ≥0.45 + возврат 1", dict(min_brk=0.45, fail_k=1))):
        tr = run(M, **kw); stats(nm, tr, B.START, tg); print(loss([x for x in tr if x[0] >= B.START]))
