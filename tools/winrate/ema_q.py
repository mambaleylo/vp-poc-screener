"""EMA threshold q 0.96 (deployed) vs 0.97 / 0.98: the deployed exits (0.75 dATR at a 4h close, emergency 1.5, 1/3 at +1R,
4R, 72h), the honest order; lists saved as emaq_<q>_1.5_4.npy/json for the bundle money"""
src = open("ema_cstop.py").read().split('run("касанием 0.75 dATR (сейчас)"')[0]
src = src.replace('np.save(f"ema_cs_{hard_a}_{kh}.npy"', 'np.save(f"emaq_{QQ}_{hard_a}_{kh}.npy"').replace('open(f"ema_cs_{hard_a}_{kh}.json", "w")', 'open(f"emaq_{QQ}_{hard_a}_{kh}.json", "w")')
exec(src)
for QQ in (0.96, 0.97, 0.98):
    idx = E.cand(QQ, mask)
    idx = idx[d.pen.values[idx] >= 0.1 + DEEP * d.datr.values[idx]]
    for i in idx:
        if i in INFO: continue
        O, H, L, C = E.bars(d.sym.values[i])
        r, k, kind, ex, took = sim(O, H, L, C, int(d.j.values[i]), int(side[i]), FILL(i), float(d.datr.values[i]))
        R[i], K[i] = r, k; INFO[i] = (kind, ex, took)
    by = {}
    for i in idx: by.setdefault(d.sym.values[i], []).append(i)
    for sym_, lst in by.items():
        O_, H_, L_, C_ = E.bars(sym_)
        for i in lst:
            j = int(d.j.values[i]); OPEN[i] = O_[j] if j < len(O_) else np.nan
    NEAR = side * (OPEN - np.array([FILL(i) if i in INFO else np.nan for i in range(len(d))])) / (d.lv.values * d.datr.values / 100)
    run(f"EMA q{QQ}", 1.5, 4)
