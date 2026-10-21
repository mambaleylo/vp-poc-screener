"""the live-like universe: at every signal only the coins in the top N by the last 30 days' volume among the 211 (the bot
scans Gate's top N by 24h volume) — breakout and P/R, vs the hand-picked 127"""
import sys
MOD = sys.argv[1]
import numpy as np
from wr_eval import stats
from mk import ts
from volrank import rank_at
def yrs(tr, y0):
    r = np.array([x[2] for x in tr]); t = np.array([x[0] for x in tr])
    return " ".join(f"{r[(t >= ts(y)) & (t < ts(y + 1))].mean():+.2f}" for y in range(y0, 2027))
if MOD == "rbx":
    import rb_h as B, mfeat
    from rb_x2 import run
    NEW = set(open("new_coins.txt").read().split()); isnew = np.array([s in NEW for s in B.SYM])
    LS = mfeat.at(B.SYM, B.T + B.TF * 3600 - 3600)[:, mfeat.NAMES.index("ls_d24")] * B.SD
    OK = ~(LS > 0.0918); RK = rank_at(B.SYM, B.T)
    for nm_, M, tg in (("бот", B.BOT, 0.45), ("проверка", B.CHECK, 0.50)):
        print(f"\n=== пробой {nm_}", flush=True)
        for lab, m in (("127 вручную (бэктест)", ~isnew), ("топ-120 по объёму (как бот)", RK <= 120), ("топ-60", RK <= 60), ("топ-30", RK <= 30),
                       ("127 и в топ-120", ~isnew & (RK <= 120))):
            tr = run(M & OK & m); print("   годы", yrs(tr, 2021)); stats(lab, tr, B.START, tg)
else:
    import prmore as PM
    for D_ in (PM.OLD, PM.NEW): D_["RK"] = rank_at(D_["SY"], D_["T"])
    def tr_(q, n, cap=20, only_old=False):
        sets = [PM.OLD] if only_old else [PM.OLD, PM.NEW]
        saved = [(D_, D_["BTC"].copy()) for D_ in sets]
        for D_ in sets: D_["BTC"] = D_["BTC"] & (D_["RK"] <= n)
        try: return PM.trades(sets, q, cap=cap)
        finally:
            for D_, b in saved: D_["BTC"] = b
    G = tuple(np.round(np.arange(0.005, 0.20, 0.005), 4))
    print("\n=== P/R q0.99, лимит 20", flush=True)
    for lab, n, oo in (("127 вручную", 9999, True), ("все 211", 9999, False), ("топ-200 по объёму (как бот)", 200, False), ("топ-120", 120, False), ("топ-60", 60, False)):
        tr = tr_(0.99, n, only_old=oo); print("   годы", yrs(tr, 2023)); stats(lab, tr, ts(2023), 0.45, grid=G)
