"""audit of SMC like ⚡: its backtest pool ordered the touches of one hour by the model's score (lexsort (T, -SC)) — the
bot takes them as the price reaches them. Here the same selection (the walk-forward scores, q 0.99, cap 12 a side, one
per coin & side, the bot coins, 2022+) with the touches of an hour ordered: by the score (as the list), the nearer level
to the hour's open first (the bot's order), random; the trades, R, the money (one account, the bot's leverage)"""
import sys, json, glob, os, numpy as np, warnings; warnings.filterwarnings("ignore")
sys.argv = ["x"]
from lv_wf import load_dir, ts
import lv_engine as LE
Dd = load_dir("lv2", LE.FNAMES)
F = Dd["F"]; fam = F[:, 0].astype(int); e = 2
LV, J, DATR = [], [], []
for fn in sorted(glob.glob("lv2/*.npz")):
    z = np.load(fn)
    if len(z["t"]) == 0: continue
    LV.append(z["lv"]); J.append(z["j"]); DATR.append(z["datr"])
LV, J, DATR = np.concatenate(LV), np.concatenate(J).astype(np.int64), np.concatenate(DATR)
z = np.load("smc_sc.npz", allow_pickle=True); SC = z["SC"]; THR = z["THR"].item()
T, SIDE, SYM, K, R = Dd["T"], Dd["SIDE"], Dd["SYM"], Dd["K"][e], Dd["R"][e]
yr = np.array([int(np.datetime64(int(t), "s").astype("datetime64[Y]").astype(int) + 1970) for t in T])
thr = np.array([np.quantile(THR[Y], 0.99) if Y in THR else np.inf for Y in range(1970, 2030)])
ok = (fam >= 33) & Dd["BOT"] & np.isfinite(SC) & (SC >= thr[np.clip(yr - 1970, 0, 59)]) & (T >= ts(2022))
idx = np.where(ok)[0]
# the hour's open of each candidate
OPEN = np.full(len(T), np.nan)
by = {}
for i in idx: by.setdefault(SYM[i], []).append(i)
for k, lst in by.items():
    Tb, O, H, L, C, V = LE.load_np(Dd["names"][k])
    for i in lst:
        OPEN[i] = O[J[i]] if J[i] < len(O) else np.nan
NEAR = SIDE * (OPEN - LV) / (LV * DATR / 100)   # how far the hour opened from the level, in daily ATR (smaller = reached first)
def select(order_key, cap=12):
    o = idx[np.lexsort((order_key[idx], T[idx]))]
    busy, act, out = {}, [], []
    for i in o:
        t = T[i]; key = (SYM[i], SIDE[i])
        if busy.get(key, 0) > t: continue
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == SIDE[i]) >= cap: continue
        end = t + int(K[i]) * 3600; busy[key] = end; act.append((end, SIDE[i])); out.append(i)
    return np.array(out, dtype=np.int64)
def show(nm, sel):
    r = R[sel]; y = yr[sel]
    ys = " ".join(f"{Y % 100}:{r[y == Y].mean():+.2f}({(y == Y).sum()})" for Y in range(2022, 2027))
    print(f"{nm:34s} сделок {len(sel):4d} {r.mean():+.3f}R WR {np.mean(r > 0)*100:.0f}% сумма {r.sum():+.0f}R | {ys}", flush=True)
    return sel
nh = {}
for i in idx: nh[(T[i], SIDE[i])] = nh.get((T[i], SIDE[i]), 0) + 1
print("кандидатов", len(idx), "· часов, где в одну сторону касаний > 1:", sum(1 for v in nh.values() if v > 1), "из", len(nh))
a = show("по баллу модели (как в списке)", select(-SC))
b = show("ближний уровень первым (как бот)", select(NEAR))
rng = np.random.default_rng(1)
rs = [select(rng.random(len(T))) for _ in range(5)]
for k, s_ in enumerate(rs[:2]): show(f"случайный порядок #{k + 1}", s_)
print("сделки, выбранные иначе:", len(set(a) ^ set(b)), "из", len(a))
#np.savez("smc_order.npz", a=a, b=b, T=T, R=R, K=K, SIDE=SIDE, SYM=SYM, LV=LV, DATR=DATR)
# ---- the hypothesis: per coin & side & hour arm one level only (decided at the hour's start), then the bot's order
def one_per(rank):   # rank: lower = kept
    best = {}
    for i in idx:
        k = (SYM[i], SIDE[i], T[i])
        if k not in best or rank[i] < rank[best[k]]: best[k] = i
    keep = np.zeros(len(T), bool); keep[list(best.values())] = True
    return keep
def select2(keep, order_key, cap=12):
    global idx
    idx0 = idx; idx = idx0[keep[idx0]]
    try: return select(order_key, cap)
    finally: idx = idx0
print("== на монету в час — один уровень (решается в начале часа), дальше порядок бота")
show("лучший по баллу", select2(one_per(-SC), NEAR))
show("самый дальний", select2(one_per(-NEAR), NEAR))
show("самый ближний", select2(one_per(NEAR), NEAR))
