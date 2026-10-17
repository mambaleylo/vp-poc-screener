"""raw (no model) average R per event: family x chart x stop x exit, per year"""
import glob, numpy as np
from mk import ts
import ev_engine as E
Ys, Ts, Fs, TFs, Ss, SY = [], [], [], [], [], []
for k, fn in enumerate(sorted(glob.glob("ev/*.npz"))):
    z = np.load(fn)
    Ys.append(z["Y"]); Ts.append(z["t"]); Fs.append(z["fam"]); TFs.append(z["tf"]); Ss.append(z["side"]); SY.append(np.full(len(z["t"]), k))
Y = np.concatenate(Ys); T = np.concatenate(Ts); FA = np.concatenate(Fs); TF = np.concatenate(TFs); SD = np.concatenate(Ss)
Y = np.where(np.abs(Y) > 60, np.nan, Y)
print("events", len(T))
YRS = [(2021, ts(2021), ts(2022)), (2022, ts(2022), ts(2023)), (2023, ts(2023), ts(2024)), (2024, ts(2024), ts(2025)), (2025, ts(2025), ts(2027))]
rows = []
for fi, f in enumerate(E.FAMS):
    for h in (1, 4, 24):
        m0 = (FA == fi) & (TF == h)
        for si, sk in enumerate(E.STOPS):
            for xi, ex in enumerate(E.EXITS):
                vals = []
                for y, a, b in YRS:
                    m = m0 & (T >= a) & (T < b)
                    v = Y[m, si, xi]; v = v[~np.isnan(v)]
                    vals.append((v.mean() if len(v) else np.nan, len(v)))
                rows.append((min(v[0] for v in vals), f, h, sk, ex, vals))
rows.sort(key=lambda r: -np.nan_to_num(r[0], nan=-9))
print("\n== лучшие по худшему году (без модели, все монеты, лонг+шорт) ==")
for mn, f, h, sk, ex, vals in rows[:30]:
    print(f"{f:9s} {h:2d}ч стоп {sk} {ex:5s} | " + " | ".join(f"{y}: {v[0]:+.2f}R n{v[1]}" for (y, _, _), v in zip(YRS, vals)))
print("\n== по сторонам: лучшие 1д/4ч ==")
for fi, f in enumerate(E.FAMS):
    for h in (4, 24):
        for s in (1, -1):
            m0 = (FA == fi) & (TF == h) & (SD == s)
            v = Y[m0, 0, 5]; v = v[~np.isnan(v)]
            vv = Y[m0, 0, 2]; vv = vv[~np.isnan(vv)]
            if len(v):
                print(f"{f:9s} {h:2d}ч {'лонг' if s > 0 else 'шорт'}: dc20 {v.mean():+.2f}R  t8 {vv.mean():+.2f}R  n{len(v)}")
