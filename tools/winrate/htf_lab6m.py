"""📏 HTF round 6 — the models: (a) new "level memory" features (causal: only touches whose E2 exit closed before this
touch): touches of the same family on the coin in 30 days, the last closed one's R, the coin's last 5 closed HTF touches'
mean R (same side), the market's closed HTF touches' mean R and count over 7 days (same side); (b) retraining each
quarter instead of each year (the threshold = q of the out-of-sample scores of the 365 days ending 14 days before the
period); (c) a short model on the traded exit mirrored (the "n" label for shorts). Saves the scores per variant:
htf6_<v>.npz (SC, PK = period key per event, THR = {period: ref scores})."""
import sys, json, glob, time, numpy as np, lightgbm as lgb, warnings; warnings.filterwarnings("ignore")
VAR = sys.argv[1:]
sys.argv = ["x"]
from numba import njit
from lv_wf import load_dir, ts
import lv_engine as LE
Dd = load_dir("lv2", LE.FNAMES); F = Dd["F"].astype(np.float32); fam = F[:, 0].astype(int)
T, SIDE, SYM, BOT = Dd["T"], Dd["SIDE"], Dd["SYM"], Dd["BOT"]
LV, J, DT = [], [], []
for fn in sorted(glob.glob("lv2/*.npz")):
    z = np.load(fn)
    if len(z["t"]) == 0: continue
    LV.append(z["lv"]); J.append(z["j"]); DT.append(z["datr"])
LV, J, DATR = np.concatenate(LV), np.concatenate(J).astype(np.int64), np.concatenate(DT)
HTF = fam <= 22
R2 = np.nan_to_num(Dd["R"][2], nan=0.0).astype(float); EX = T + Dd["K"][2].astype(np.int64) * 3600
# ---- (a) the level-memory features ----
t0_ = time.time()
NF = np.zeros((len(T), 5), np.float32)
idx = np.where(HTF)[0]
# 0: same coin/fam/side touches in the 30 days before; 1: the last closed one's R (0 if none)
key = SYM[idx].astype(np.int64) * 1000 + fam[idx] * 10 + (SIDE[idx] > 0)
for g in np.unique(key):
    ii = idx[key == g]; ii = ii[np.argsort(T[ii], kind="stable")]
    tt = T[ii]; NF[ii, 0] = np.arange(len(ii)) - np.searchsorted(tt, tt - 30 * 86400)
    o = ii[np.argsort(EX[ii], kind="stable")]; ex = EX[o]
    p = np.searchsorted(ex, tt, "right")
    NF[ii, 1] = np.where(p > 0, R2[o[np.maximum(p - 1, 0)]], 0.0)
# 2: the coin's last 5 closed HTF touches (same side) mean R
key2 = SYM[idx].astype(np.int64) * 10 + (SIDE[idx] > 0)
for g in np.unique(key2):
    ii = idx[key2 == g]; o = ii[np.argsort(EX[ii], kind="stable")]; ex = EX[o]; cs = np.r_[0, np.cumsum(R2[o])]
    p = np.searchsorted(ex, T[ii], "right"); a = np.maximum(p - 5, 0)
    NF[ii, 2] = np.where(p > 0, (cs[p] - cs[a]) / np.maximum(p - a, 1), 0.0)
# 3, 4: the market's closed HTF touches (same side) over 7 days: mean R, count
for sd in (1, -1):
    ii = idx[SIDE[idx] == sd]; o = ii[np.argsort(EX[ii], kind="stable")]; ex = EX[o]; cs = np.r_[0, np.cumsum(R2[o])]
    p = np.searchsorted(ex, T[ii], "right"); a = np.searchsorted(ex, T[ii] - 7 * 86400, "right")
    NF[ii, 3] = np.where(p > a, (cs[p] - cs[a]) / np.maximum(p - a, 1), 0.0); NF[ii, 4] = np.log1p(p - a)
print("признаки памяти", round(time.time() - t0_), "с; средние", NF[idx].mean(0).round(3).tolist(), flush=True)
# ---- the labels ----
zn = np.load("htf_long_sc.npz", allow_pickle=True); RL = zn["RL"]
@njit
def wk2(O, H, L, C, Tb, j, s, fill, datr, hard_a, take, hold, kh):
    risk = fill * datr / 100; ssl = fill - s * risk; hsl = fill - s * hard_a * risk; tp = fill + s * take * risk
    n = len(C); e = min(n, j + hold)
    for q in range(e - j):
        b = j + q
        if (s > 0 and L[b] <= hsl) or (s < 0 and H[b] >= hsl):
            x = O[b] if (q > 0 and ((s > 0 and O[b] <= hsl) or (s < 0 and O[b] >= hsl))) else hsl
            return s * (x - fill) / risk - (0.001 + 0.0003 * (q + 1) / 24) * fill / risk
        if q > 0 and ((s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp)):
            return s * (tp - fill) / risk - (0.001 + 0.0003 * (q + 1) / 24) * fill / risk
        if (Tb[b] + 3600) % (kh * 3600) == 0 and ((s > 0 and C[b] <= ssl) or (s < 0 and C[b] >= ssl)):
            return s * (C[b] - fill) / risk - (0.001 + 0.0003 * (q + 1) / 24) * fill / risk
    b = e - 1
    return s * (C[b] - fill) / risk - (0.001 + 0.0003 * (e - j) / 24) * fill / risk
LONG = HTF & (SIDE > 0) & (T >= ts(2019)) & np.isfinite(DATR)
SHORT = HTF & (SIDE < 0) & (T >= ts(2019)) & np.isfinite(DATR)
def short_label():
    fn = "htf6_short_label.npy"
    try: return np.load(fn)
    except FileNotFoundError: pass
    RS = np.full(len(T), np.nan); ii = np.where(SHORT)[0]
    for k in sorted(set(SYM[ii])):
        Tb, O, H, L, C, V = LE.load_np(Dd["names"][k])
        for i in ii[SYM[ii] == k]: RS[i] = wk2(O, H, L, C, Tb, int(J[i]), -1, float(LV[i]), float(DATR[i]), 3.0, 3.0, 96, 4)
    np.save(fn, RS); print("шорт-метка: событий", len(ii), "ср.R", round(float(np.nanmean(RS[ii])), 3), flush=True)
    return RS
pr = dict(n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=300, subsample=0.7, subsample_freq=1,
          colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
def wf(X, y, mask, quarterly):
    """walk-forward: train on the bot coins' events before the period start - 14 days; ref = the OOS scores of the 365
    days before that (the previous year's for yearly, as lv_wf.scores)"""
    y = np.nan_to_num(y, nan=0.0).clip(-1.2, 6.0)
    starts = ([ts(Y, m) for Y in range(2022, 2027) for m in (1, 4, 7, 10)] if quarterly else [ts(Y) for Y in range(2022, 2027)])
    starts = [s for s in starts if s < ts(2026, 10)]
    SC = np.full(len(T), np.nan); PK = np.full(len(T), -1, np.int64); THR = {}
    for k, s in enumerate(starts):
        e = starts[k + 1] if k + 1 < len(starts) else ts(2027)
        tr = mask & BOT & (T < s - 14 * 86400)
        sc = np.zeros(len(T), np.float32); te = mask & (T >= s) & (T < e)
        for sd in range(2):
            m = lgb.LGBMRegressor(random_state=sd, **pr).fit(X[tr], y[tr]); sc[te | (mask & BOT & (T >= s - 380 * 86400) & (T < s))] += m.predict(X[te | (mask & BOT & (T >= s - 380 * 86400) & (T < s))]) / 2
        SC[te] = sc[te]; PK[te] = s
        ref = mask & BOT & (T >= (s - 365 * 86400 if quarterly else ts(int(np.datetime64(int(s), 's').astype('datetime64[Y]').astype(int) + 1970) - 1))) & (T < s - 14 * 86400)
        oos = ref & np.isfinite(SC)
        THR[s] = SC[oos] if oos.sum() >= 200 else sc[ref]
        print(f"   период {np.datetime64(int(s), 's').astype('datetime64[D]')} обучено {int(tr.sum())} тест {int(te.sum())} реф {int(ref.sum())}{' (OOS)' if oos.sum() >= 200 else ' (in-sample)'}", flush=True)
    return SC, PK, THR
XN = np.hstack([F, NF])
for v in VAR:
    t1 = time.time()
    X = XN if "m" in v else F
    quarterly = "q" in v
    if v.startswith("o"): y, mask = Dd["R"][2], HTF
    elif v.startswith("n"): y, mask = RL, LONG
    else: y, mask = short_label(), SHORT
    print(f"== {v}: {'новые признаки' if 'm' in v else 'старые признаки'}, {'раз в квартал' if quarterly else 'раз в год'}, событий {int(mask.sum())}", flush=True)
    SC, PK, THR = wf(X, y, mask, quarterly)
    np.savez(f"htf6_{v}.npz", SC=SC, PK=PK, THR=np.array(THR, dtype=object))
    print(f"   готово за {round(time.time() - t1)} с", flush=True)
