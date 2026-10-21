"""📈 breakout on all 211 coins by the coin's age at the signal (its first Binance 1h candle): young coins break out badly"""
import numpy as np
import rb_h as B, mfeat
from rb_x2 import run
from wr_eval import stats
from common import load
FIRST = {s: load(s)[0]["time"] for s in set(B.SYM)}
AGE = (B.T - np.array([FIRST[s] for s in B.SYM])) / 86400
NEW = set(open("new_coins.txt").read().split()); isnew = np.array([s in NEW for s in B.SYM])
LS = mfeat.at(B.SYM, B.T + B.TF * 3600 - 3600)[:, mfeat.NAMES.index("ls_d24")] * B.SD
OK = ~(LS > 0.0918)
for nm_, M, tg in (("бот", B.BOT, 0.45), ("проверка", B.CHECK, 0.50)):
    print(f"\n=== пробой {nm_}", flush=True)
    stats("127 монет (сейчас)", run(M & OK & ~isnew), B.START, tg)
    for days in (0, 180, 365, 540, 730):
        stats(f"все 211, монете ≥ {days} дн.", run(M & OK & (AGE >= days)), B.START, tg)
        stats(f"   только 127, ≥ {days} дн.", run(M & OK & (AGE >= days) & ~isnew), B.START, tg)
        stats(f"   только новые, ≥ {days} дн.", run(M & OK & (AGE >= days) & isnew), B.START, tg)
