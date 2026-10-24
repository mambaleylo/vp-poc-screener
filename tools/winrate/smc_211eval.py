"""the bot's reach filter (|px - lv| <= 1.5 dATR at the hour's start) applied before the pool. SMC threshold q 0.99 (deployed) vs 0.993 / 0.995: the close-stop exits (1 dATR at a 4h close, emergency 2, take 3R, 72h),
the honest order; then the bundle money with the v0.99.704 rules"""
import numpy as np
src = open("smc_cstop.py").read().split('run("касанием 1 dATR (сейчас)"')[0]
src = src.replace('np.save(f"smc_cs_{soft_a}_{hard_a}_{kh}.npy"', 'np.save(f"smcqr_m211_{UNIV}_{QTAG}_{soft_a}_{hard_a}_{kh}.npy"')
exec(src)
z = np.load("smc_sc211.npz", allow_pickle=True); SC = z["SC"]; THR = z["THR"].item()   # the 211-coin model's scores
od = open("smc_order.py").read()
for UNIV, q in ((127, 0.99), (127, 0.993), (211, 0.99), (211, 0.993)):
    QTAG = q
    thr = np.array([np.quantile(THR[Y], q) if Y in THR else np.inf for Y in range(1970, 2030)])
    idx = np.where((fam >= 33) & (Dd["BOT"] | (UNIV == 211)) & np.isfinite(SC) & (SC >= thr[np.clip(yr - 1970, 0, 59)]) & (T >= ts(2022)))[0]
    OPEN = np.full(len(T), np.nan); by = {}
    for i in idx: by.setdefault(SYM[i], []).append(i)
    for k, lst in by.items():
        Tb, O, H, L, C, V = LE.load_np(Dd["names"][k])
        for i in lst: OPEN[i] = O[J[i]] if J[i] < len(O) else np.nan
    NEAR = SIDE * (OPEN - LV) / (LV * DATR / 100)
    PX = np.full(len(T), np.nan)
    for k, lst in by.items():
        Tb, O, H, L, C, V = LE.load_np(Dd["names"][k])
        for i in lst: PX[i] = C[J[i] - 1] if J[i] >= 1 else np.nan
    reach = np.abs(PX[idx] - LV[idx]) / PX[idx] * 100 <= 1.5 * DATR[idx]
    print(f"q{q}: в досягаемости {reach.mean()*100:.0f}% кандидатов", flush=True)
    idx = idx[reach]
    run(f"SMC модель-211, монет {UNIV}, q{q}", 1.0, 2.0, 4)
