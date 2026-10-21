"""📈 breakout on more coins: the v0.99.667 rule (strong breakouts >= 0.6 ATR, the limit 0.2 ATR / 3 bars, the fail exit,
a quarter at +1R, the crowd filter) on the 127 coins, the 84 extra Binance coins (new_coins.txt) and all together"""
import numpy as np
import rb_h as B, mfeat
from rb_x2 import run
from wr_eval import stats
from mk import ts
NEW = set(open("new_coins.txt").read().split())
isnew = np.array([s in NEW for s in B.SYM])
LS = mfeat.at(B.SYM, B.T + B.TF * 3600 - 3600)[:, mfeat.NAMES.index("ls_d24")] * B.SD
OK = ~(LS > 0.0918)
def yrs(tr):
    r = np.array([x[2] for x in tr]); t = np.array([x[0] for x in tr])
    return " ".join(f"{r[(t >= ts(y)) & (t < ts(y + 1))].mean():+.2f}" for y in range(2021, 2027))
print("events: old", int((~isnew).sum()), "new", int(isnew.sum()))
for nm_, M, tg in (("бот", B.BOT, 0.45), ("проверка", B.CHECK, 0.50)):
    print(f"\n=== пробой {nm_}", flush=True)
    for lab, m, cap in (("127 монет (сейчас)", ~isnew, 6), ("новые 84", isnew, 6), ("все 211", np.ones(len(B.T), bool), 6), ("все 211, лимит 8", np.ones(len(B.T), bool), 8)):
        tr = run(M & OK & m, cap=cap); print("   годы", yrs(tr)); stats(lab, tr, B.START, tg)
