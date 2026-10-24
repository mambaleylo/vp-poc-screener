"""SMC: the stop on a candle's close (as ⚡ v0.99.694) on the honest pool (the bot's touch order): the soft stop 1 daily ATR
by the close of a 1h / 4h / 1d candle (UTC), the hard stop 1.5 / 2 dATR by a touch; the take 3R of the soft one, 72 h;
R per the soft stop (the size), the pool re-selected with the new trade lengths"""
exec(open("smc_order.py").read().split("def show(")[0])
from numba import njit
@njit
def wk(O, H, L, C, Tb, j, s, fill, datr, soft_a, hard_a, take, hold, kh):
    risk = fill * soft_a * datr / 100; ssl = fill - s * risk; hsl = fill - s * hard_a * datr / 100 * fill; tp = fill + s * take * risk
    n = len(C); e = min(n, j + hold)
    for q in range(e - j):
        b = j + q
        if (s > 0 and L[b] <= hsl) or (s < 0 and H[b] >= hsl):
            x = O[b] if (q > 0 and ((s > 0 and O[b] <= hsl) or (s < 0 and O[b] >= hsl))) else hsl
            return s * (x - fill) / risk - (0.001 + 0.0003 * (q + 1) / 24) * fill / risk, q + 1, 0
        if q > 0 and ((s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp)):
            return s * (tp - fill) / risk - (0.0007 + 0.0003 * (q + 1) / 24) * fill / risk, q + 1, 1
        if kh > 0 and (Tb[b] + 3600) % (kh * 3600) == 0 and ((s > 0 and C[b] <= ssl) or (s < 0 and C[b] >= ssl)):
            return s * (C[b] - fill) / risk - (0.001 + 0.0003 * (q + 1) / 24) * fill / risk, q + 1, 4
    b = e - 1
    return s * (C[b] - fill) / risk - (0.001 + 0.0003 * (e - j) / 24) * fill / risk, e - j, 3
BARS = {}
def bars_of(k):
    if k not in BARS:
        Tb, O, H, L, C, V = LE.load_np(Dd["names"][k]); BARS.clear(); BARS[k] = (Tb, O, H, L, C)
    return BARS[k]
def variant(soft_a, hard_a, kh):
    Rn = np.full(len(T), np.nan); Kn = np.zeros(len(T), np.int64); KD = np.zeros(len(T), np.int64)
    for k in sorted(set(SYM[idx])):
        Tb, O, H, L, C = bars_of(k)
        for i in idx[SYM[idx] == k]:
            r, kk, kd = wk(O, H, L, C, Tb, int(J[i]), int(SIDE[i]), float(LV[i]), float(DATR[i]), soft_a, hard_a, 3.0, 72, kh)
            Rn[i], Kn[i], KD[i] = r, kk, kd
    return Rn, Kn, KD
def run(nm, soft_a, hard_a, kh):
    global R, K
    R0, K0 = R, K
    R, K, KD = variant(soft_a, hard_a, kh)
    sel = select(NEAR); r = R[sel]; y = yr[sel]
    ys = " ".join(f"{Y % 100}:{r[y == Y].mean():+.2f}" for Y in range(2022, 2027))
    print(f"{nm:36s} сделок {len(sel):4d} {r.mean():+.3f}R WR {np.mean(r > 0)*100:.0f}% стоп-закр {np.mean(KD[sel] == 4)*100:.0f}% авар {np.mean(KD[sel] == 0)*100:.0f}% | {ys}", flush=True)
    np.save(f"smc_cs_{soft_a}_{hard_a}_{kh}.npy", np.c_[sel, T[sel], T[sel] + K[sel] * 3600, R[sel], DATR[sel] * soft_a / 100, DATR[sel] * hard_a / 100, SYM[sel]])
    R, K = R0, K0
run("касанием 1 dATR (сейчас)", 1.0, 1.0, 0)
for kh in (1, 4, 24):
    for hard in (1.5, 2.0):
        run(f"закр. {kh}ч за 1, авар. {hard}", 1.0, hard, kh)
