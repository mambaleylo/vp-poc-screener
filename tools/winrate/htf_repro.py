"""is HTF's deployed model reproducible? htf_export.py's recipe: "o" = the HTF levels (lv2 fam <= 22, both sides), label E2;
"n" = the long HTF touches (2019+), label = the traded exit (soft stop 1 dATR at a 4h close, hard 3 dATR, take 3R, 96 h);
2 LightGBM each, the bot coins' events closed 14 days before 2026 -> the scores vs the deployed trees on the 2026 long HTF
touches: the correlation, the picks (either model over its threshold), the R of the picks (the traded exit)"""
import os, sys, json, glob, numpy as np, lightgbm as lgb, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "new_ind"))
from numba import njit
from lv_wf import load_dir, ts
import lv_engine as LE, treevec as TV
M = json.load(open(os.path.join(HERE, "..", "..", "vp_htf_model.json")))
print("feats same:", M["feats"] == LE.FNAMES, "thr", M["thr_o"], M["thr_n"], flush=True)
Dd = load_dir("lv2", LE.FNAMES); F = Dd["F"]; fam = F[:, 0].astype(int); T, SIDE, SYM, BOT = Dd["T"], Dd["SIDE"], Dd["SYM"], Dd["BOT"]
LV, J, DT = [], [], []
for fn in sorted(glob.glob("lv2/*.npz")):
    z = np.load(fn)
    if len(z["t"]) == 0: continue
    LV.append(z["lv"]); J.append(z["j"]); DT.append(z["datr"])
LV, J, DATR = np.concatenate(LV), np.concatenate(J).astype(np.int64), np.concatenate(DT)
@njit
def wk2(O, H, L, C, Tb, j, fill, datr, hard_a, take, hold, kh):
    risk = fill * datr / 100; ssl = fill - risk; hsl = fill - hard_a * risk; tp = fill + take * risk
    n = len(C); e = min(n, j + hold)
    for q in range(e - j):
        b = j + q
        if L[b] <= hsl:
            x = O[b] if (q > 0 and O[b] <= hsl) else hsl
            return (x - fill) / risk - (0.001 + 0.0003 * (q + 1) / 24) * fill / risk
        if q > 0 and H[b] >= tp:
            return (tp - fill) / risk - (0.001 + 0.0003 * (q + 1) / 24) * fill / risk
        if (Tb[b] + 3600) % (kh * 3600) == 0 and C[b] <= ssl:
            return (C[b] - fill) / risk - (0.001 + 0.0003 * (q + 1) / 24) * fill / risk
    b = e - 1
    return (C[b] - fill) / risk - (0.001 + 0.0003 * (e - j) / 24) * fill / risk
HTF = fam <= 22
LONG = HTF & (SIDE > 0) & (T >= ts(2019)) & np.isfinite(DATR)
RL = np.full(len(T), np.nan); idx = np.flatnonzero(LONG)
for k in sorted(set(SYM[idx])):
    Tb, O, H, L, C, V = LE.load_np(Dd["names"][k])
    for i in idx[SYM[idx] == k]:
        if J[i] < len(C): RL[i] = wk2(O, H, L, C, Tb, int(J[i]), float(LV[i]), float(DATR[i]), 3.0, 3.0, 96, 4)
print("RL done", flush=True)
CUT = ts(2026) - 14 * 86400
pr = dict(n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=300, subsample=0.7, subsample_freq=1, colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
te = np.flatnonzero(LONG & BOT & (T >= ts(2026)))
res = {}
for key, mask, y in (("o", HTF, np.nan_to_num(Dd["R"][2], nan=0.0).clip(-1.2, 6.0)), ("n", LONG, np.nan_to_num(RL, nan=0.0).clip(-1.2, 6.0))):
    tr = mask & BOT & (T < CUT)
    a = np.mean([lgb.LGBMRegressor(random_state=s, **pr).fit(F[tr], y[tr]).predict(F[te]) for s in range(2)], axis=0)
    b = TV.model_score(M["models_" + key], F[te].astype(float))
    res[key] = (a, b, float(M["thr_" + key]))
    print(f"модель {key}: обучающих {int(tr.sum())}, корреляция оценок на длинных касаниях 2026 {np.corrcoef(a, b)[0, 1]:.4f}", flush=True)
pa = (res["o"][0] >= res["o"][2]) | (res["n"][0] >= res["n"][2]); pb = (res["o"][1] >= res["o"][2]) | (res["n"][1] >= res["n"][2])
R = RL[te]
f_ = lambda m_: f"{np.nanmean(R[m_]):+.3f}R ({int(m_.sum())})" if m_.any() else "—"
print(f"отбор 2026 (порог бота): пересборка {f_(pa)}, бот {f_(pb)}, общих {int((pa & pb).sum())}", flush=True)
print("htf repro done", flush=True)
