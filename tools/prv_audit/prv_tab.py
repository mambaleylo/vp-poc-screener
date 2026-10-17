"""Peak Reversal audit tables from prv/*.npz (monthly n / sum R / wins per config x label per coin)"""
import glob, json, numpy as np
from prv_build import CONFIGS, LABELS, NM
files = sorted(glob.glob("prv/*.npz"))
N = S = W = None
PC = {}
for fn in files:
    z = np.load(fn)
    N = z["N"].astype(np.int64) if N is None else N + z["N"]
    S = z["S"].astype(np.float64) if S is None else S + z["S"]
    W = z["W"].astype(np.int64) if W is None else W + z["W"]
    PC[fn.split("/")[-1][:-4]] = (z["N"], z["S"])
print("coins", len(files))
def yr(y):   # month slice of a year (2026: Jan..Sep)
    a = (y - 2020) * 12
    return slice(a, min(a + 12, (2026 - 2020) * 12 + 9))
WEEKS = {y: (52.14 if y < 2026 else 39.0) for y in range(2020, 2027)}
def st(ci, li, years):
    n = sum(N[ci, li, yr(y)].sum() for y in years); s = sum(S[ci, li, yr(y)].sum() for y in years)
    w = sum(W[ci, li, yr(y)].sum() for y in years); wk = sum(WEEKS[y] for y in years)
    return n, (s / n if n else np.nan), s, (w / n * 100 if n else np.nan), n / wk
def dd(ci, li, years):
    m = np.concatenate([S[ci, li, yr(y)] for y in years]); c = np.cumsum(m)
    return float(np.max(np.maximum.accumulate(np.concatenate([[0], c])) - np.concatenate([[0], c])))
def name(ci, li):
    tf, (mt, ln), mult, kind = CONFIGS[ci]; sk, tk, hd = LABELS[li]
    return f"{tf} {mt}{ln} ×{mult} {kind} | стоп {sk}{'ATR' if sk != 'ext' else ''} тейк {tk}{'R' if tk != 'mid' else ''} {hd}б"
def row(ci, li):
    out = []
    for ys in ((2021,), (2022,), (2023,), (2024,), (2025, 2026)):
        n, a, s, w, wk = st(ci, li, ys)
        out.append(f"{a:+.2f}R {wk:.0f}/нед")
    n, a, s, w, wk = st(ci, li, (2025, 2026))
    return " | ".join(out) + f" | 25–26: WR{w:.0f} Σ{s:.0f} dd{dd(ci, li, (2025, 2026)):.0f}"
# 1. the bot's family as it is (wick, stop 1 ATR, hold 48, takes 1..3) — all coins, no selection
print("\n== бот как есть (касание фитилём, стоп 1 ATR, 48 баров), все монеты без отбора ==")
for ci, (tf, b, mult, kind) in enumerate(CONFIGS):
    if kind == "wick" and b == ("EMA", 20) and mult == 2.0:
        for li, (sk, tk, hd) in enumerate(LABELS):
            if sk == 1.0 and hd == 48 and tk in (1.0, 1.5, 2.0, 3.0):
                print(name(ci, li), "||", row(ci, li))
# 2. pick on 2021–23 only, judge on 2024 and 2025–26
print("\n== лучшие по 2021–23 (выбор только по ним), проверка 2024 и 2025–26 ==")
cand = []
for ci in range(len(CONFIGS)):
    for li in range(len(LABELS)):
        n, a, s, w, wk = st(ci, li, (2021, 2022, 2023))
        ok = all(st(ci, li, (y,))[0] >= 100 for y in (2021, 2022, 2023))
        if ok:
            mins = min(st(ci, li, (y,))[1] for y in (2021, 2022, 2023))
            cand.append((mins, a, ci, li))
cand.sort(reverse=True)
for mins, a, ci, li in cand[:15]:
    print(name(ci, li), "||", row(ci, li))
# 3. marginal effects over 2021–2026: mean of the per-combo avg R
print("\n== влияние каждого выбора (среднее по всем остальным вариантам, 2021–2026) ==")
allys = (2021, 2022, 2023, 2024, 2025, 2026)
A = np.array([[st(ci, li, allys)[1] for li in range(len(LABELS))] for ci in range(len(CONFIGS))])
def marg(label, keyf, axis):
    vals = {}
    for i in range(A.shape[axis]):
        k = keyf(i)
        v = A[i] if axis == 0 else A[:, i]
        vals.setdefault(k, []).append(np.nanmean(v))
    print(label + ": " + " · ".join(f"{k}: {np.mean(v):+.3f}R" for k, v in vals.items()))
marg("график", lambda i: CONFIGS[i][0], 0)
marg("средняя", lambda i: f"{CONFIGS[i][1][0]}{CONFIGS[i][1][1]}", 0)
marg("полоса", lambda i: f"×{CONFIGS[i][2]}", 0)
marg("вход", lambda i: CONFIGS[i][3], 0)
marg("стоп", lambda i: str(LABELS[i][0]), 1)
marg("тейк", lambda i: str(LABELS[i][1]), 1)
marg("держать", lambda i: f"{LABELS[i][2]} баров", 1)
# 4. the bot's method: per coin, every month the best of its 216-like combos on the trailing 12 months -> next month
print("\n== метод бота: у каждой монеты лучший вариант за прошлые 12 мес. → торгуем следующий месяц ==")
bot_ci = [ci for ci, (tf, b, mult, kind) in enumerate(CONFIGS) if kind == "wick" and mult in (1.5, 2.0, 2.5)]
bot_li = [li for li, (sk, tk, hd) in enumerate(LABELS) if sk == 1.0 and hd == 48 and tk in (1.0, 1.5, 2.0, 3.0)]
for min_n, min_avg in ((15, 0.0), (15, 0.2), (30, 0.3)):
    res = {y: [0, 0.0] for y in range(2021, 2027)}
    for sym, (n_, s_) in PC.items():
        for mth in range(12, 6 * 12 + 9):
            best = None
            for ci in bot_ci:
                for li in bot_li:
                    n0 = n_[ci, li, mth - 12:mth].sum()
                    if n0 >= min_n:
                        a0 = s_[ci, li, mth - 12:mth].sum() / n0
                        if a0 > min_avg and (best is None or a0 > best[0]):
                            best = (a0, ci, li)
            if best:
                y = 2020 + mth // 12
                res[y][0] += int(n_[best[1], best[2], mth]); res[y][1] += float(s_[best[1], best[2], mth])
    print(f"порог: ≥{min_n} сделок, в среднем >{min_avg}R: " + " | ".join(f"{y}: {v[1] / v[0] if v[0] else 0:+.2f}R {v[0] / WEEKS[y]:.0f}/нед" for y, v in res.items()))
