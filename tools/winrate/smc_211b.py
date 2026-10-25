"""SMC on the 211 coins (the bot trades 127): the deployed model (trained on the 127 — the 84 others unseen) and the 211-coin model, the v0.99.709 rules (q 0.993, take 3R, 96 h, the 4h close stop 1 dATR, emergency 2, reach 1.5 dATR). Was: the bot's reach filter (|px - lv| <= 1.5 dATR at the hour's start) applied before the pool. SMC threshold q 0.99 (deployed) vs 0.993 / 0.995: the close-stop exits (1 dATR at a 4h close, emergency 2, take 3R, 72h),
the honest order; then the bundle money with the v0.99.704 rules"""
import numpy as np
src = open("smc_cstop.py").read().split('run("касанием 1 dATR (сейчас)"')[0]
src = src.replace('np.save(f"smc_cs_{soft_a}_{hard_a}_{kh}.npy"', 'np.save(f"smcqu_{TAG}_{soft_a}_{hard_a}_{kh}.npy"')
exec(src)
od = open("smc_order.py").read()
SC0, THR0 = SC, THR
z = np.load("smc_sc211.npz", allow_pickle=True); SC211, THR211 = z["SC"], z["THR"].item()
q = 0.993
for TAG, (SC, THR, UNIV) in (("m127_u127", (SC0, THR0, 127)), ("m127_u211", (SC0, THR0, 211)), ("m211_u127", (SC211, THR211, 127)), ("m211_u211", (SC211, THR211, 211))):
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
    idx = idx[reach]
    src_v = open("smc_cstop.py").read().split("def variant(")[1].split("def run(")[0].replace("3.0, 72, kh)", "3.0, 96, kh)")
    exec("def variant(" + src_v)
    run(f"SMC {TAG}", 1.0, 2.0, 4)
