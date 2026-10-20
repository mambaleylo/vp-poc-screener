import rb_h as B
from rb_fail import run
from wr_eval import stats
for nm_, M, tg in (("бот", B.BOT & (B.BRK >= 0.6), 0.45), ("проверка", B.CHECK & (B.BRK >= 0.6), 0.50)):
    print(f"\n=== пробой (сильные, выход по возврату 2), {nm_}")
    for nm, kw in (("сейчас (по рынку)", {}), ("лимитка −0.2 ATR, 3 свечи", dict(entry="lim", retest=2)), ("лимитка −0.3 ATR", dict(entry="lim", retest=3)),
                   ("лимитка −0.5 ATR", dict(entry="lim", retest=5))):
        stats(nm, run(M, fail_k=2, **kw), B.START, tg)
