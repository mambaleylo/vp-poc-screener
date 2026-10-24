"""SMC threshold q 0.99 (deployed) vs 0.993 / 0.995: the close-stop exits (1 dATR at a 4h close, emergency 2, take 3R, 72h),
the honest order; then the bundle money with the v0.99.704 rules"""
import numpy as np
src = open("smc_cstop.py").read().split('run("касанием 1 dATR (сейчас)"')[0]
src = src.replace('np.save(f"smc_cs_{soft_a}_{hard_a}_{kh}.npy"', 'np.save(f"smcq_{QTAG}_{soft_a}_{hard_a}_{kh}.npy"')
exec(src)
od = open("smc_order.py").read()
for q in (0.991, 0.992, 0.994):
    QTAG = q
    thr = np.array([np.quantile(THR[Y], q) if Y in THR else np.inf for Y in range(1970, 2030)])
    idx = np.where((fam >= 33) & Dd["BOT"] & np.isfinite(SC) & (SC >= thr[np.clip(yr - 1970, 0, 59)]) & (T >= ts(2022)))[0]
    OPEN = np.full(len(T), np.nan); by = {}
    for i in idx: by.setdefault(SYM[i], []).append(i)
    for k, lst in by.items():
        Tb, O, H, L, C, V = LE.load_np(Dd["names"][k])
        for i in lst: OPEN[i] = O[J[i]] if J[i] < len(O) else np.nan
    NEAR = SIDE * (OPEN - LV) / (LV * DATR / 100)
    run(f"SMC q{q}", 1.0, 2.0, 4)
