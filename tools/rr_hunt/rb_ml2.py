"""📈 breakout, round 4: a walk-forward LightGBM that scores every breakout (the Neuro features + range width, break
strength, range length, chart, side) on the v0.99.663 rule's R (limit 0.2 ATR / 3 bars, stop 2 ATR, a quarter at +1R,
fail exit 2, channel 20 / 15); each year's model sees only trades that closed before the year; the threshold = a
quantile of the previous year's scores. Compared with the rule's own filter (break >= 0.6 ATR) on the bot's and the
check set from 2022."""
import os, numpy as np, lightgbm as lgb
SEED = int(os.environ.get('SEED', 0))
import rb_h as B
from rb_sim2 import bars, NEX
from rb_x2 import sim
from wr_eval import stats
from mk import ts
M = B.OWN & (B.RG < 4.0)
R = np.full(len(B.T), np.nan); Hh = np.ones(len(B.T), np.int64)
for i in np.where(M)[0]:
    tfh = int(B.TF[i]); O, H, L, C, T, atr, LO, HI, e200 = bars(B.SYM[i], tfh)
    j = int(np.searchsorted(T, B.T[i]))
    if j >= len(T) - 4 or T[j] != B.T[i] or atr[j] != atr[j]: continue
    s = int(B.SD[i]); N0 = int(B.N[i]); a = float(atr[j])
    lvl = H[j - N0:j].max() if s > 0 else L[j - N0:j].min()
    lv_ = O[j + 1] - s * 0.2 * a; q0 = -1
    for q in range(1, 4):
        if j + q >= len(C): break
        if (s > 0 and L[j + q] <= lv_) or (s < 0 and H[j + q] >= lv_): q0 = q; break
    if q0 < 0: R[i] = 0.0; Hh[i] = 3; continue      # no fill: 0 for the label, skipped in the replay below
    i0 = j + q0; e = min(O[i0], lv_) if s > 0 else max(O[i0], lv_)
    r, k = sim(O, H, L, C, LO, HI, i0, e, s, 2.0 * a, 180 if tfh == 24 else 360, tfh, NEX.index(20), NEX.index(15), 4.0, 1.0, 0.25, lvl, 2, 0.0)
    R[i], Hh[i] = r, k + (i0 - j - 1)
FILL = ~np.isnan(R) & ~((R == 0) & (Hh == 3))
END = B.T + Hh * B.TF * 3600
XF = np.column_stack([B.X, B.RG, B.BRK, B.N, B.TF, B.SD]).astype(np.float32)
y = np.nan_to_num(R, nan=0.0).clip(-1.5, 10.0)
SC = np.full(len(B.T), np.nan); THR = {}
for Y in (2022, 2023, 2024, 2025):
    tr = M & ~np.isnan(R) & (END < ts(Y))
    te = M & (B.T >= ts(Y)) & (B.T < (ts(Y + 1) if Y < 2025 else ts(2027)))
    ref = M & (B.T >= ts(Y - 1)) & (B.T < ts(Y))
    p = np.zeros(len(B.T))
    for s_ in range(3):
        p += lgb.LGBMRegressor(n_estimators=400, learning_rate=0.02, num_leaves=15, min_child_samples=100, subsample=0.7, subsample_freq=1,
                               colsample_bytree=0.6, reg_lambda=5.0, verbose=-1, n_jobs=2, random_state=SEED + s_).fit(XF[tr], y[tr]).predict(XF) / 3
    SC[te] = p[te]; THR[Y] = {q: float(np.quantile(p[ref], q)) for q in (0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.7, 0.8)}
    print(Y, "train", int(tr.sum()), flush=True)
YR = np.minimum(np.array([int(np.datetime64(int(t), "s").astype("datetime64[Y]").astype(int) + 1970) for t in B.T]), 2025)
def thr(q): return np.array([THR[y][q] if y in THR else np.inf for y in YR])
def trades(mask):
    m = mask & FILL & ~np.isnan(SC)
    tr = B.replay(m, R, Hh, cap=6)
    return [(int(B.T[i]), int(END[i]), float(R[i]), int(B.SD[i]), int(i)) for i in tr]
def yrs(tr):
    r = np.array([x[2] for x in tr]); t = np.array([x[0] for x in tr])
    return " ".join(f"{r[(t >= ts(y)) & (t < ts(y + 1))].mean():+.2f}" for y in (2022, 2023, 2024, 2025))
for nm_, S, tg in (("бот", B.BOT, 0.45), ("проверка", B.CHECK, 0.50)):
    print(f"\n=== пробой с 2022, {nm_}, seed {SEED}", flush=True)
    tr = trades(S & (B.BRK >= 0.6)); print("   годы", yrs(tr)); stats("правило: сила ≥ 0.6 ATR (v663)", tr, ts(2022), tg)
    for q in (0.2, 0.25, 0.3, 0.35, 0.4):
        tr = trades(S & (B.BRK >= 0.6) & (SC >= thr(q))); print("   годы", yrs(tr)); stats(f"сила ≥ 0.6 + отсечь худшие {round(q * 100)}%", tr, ts(2022), tg)
np.savez(f"rb_ml_sc_{SEED}.npz", SC=SC, R=R)
