"""SMC: the model's threshold lower -> more trades? The honest order (the nearer level first), the cap 12 a side; R of the
research's exit E2 (the touch stop, as a relative measure) by the score's band"""
src = open("smc_order.py").read()
pre = src.split("ok = (fam >= 33)")[0]
exec(pre)
for q in (0.99, 0.993, 0.995):
    thr = np.array([np.quantile(THR[Y], q) if Y in THR else np.inf for Y in range(1970, 2030)])
    ok = (fam >= 33) & Dd["BOT"] & np.isfinite(SC) & (SC >= thr[np.clip(yr - 1970, 0, 59)]) & (T >= ts(2022))
    idx = np.where(ok)[0]
    OPEN = np.full(len(T), np.nan); by = {}
    for i in idx: by.setdefault(SYM[i], []).append(i)
    for k, lst in by.items():
        Tb, O, H, L, C, V = LE.load_np(Dd["names"][k])
        for i in lst: OPEN[i] = O[J[i]] if J[i] < len(O) else np.nan
    NEAR = SIDE * (OPEN - LV) / (LV * DATR / 100)
    exec("def select" + src.split("def select")[1].split("def show")[0])
    exec("def show" + src.split("def show")[1].split("nh = {}")[0])
    show(f"q{q}", select(NEAR))
