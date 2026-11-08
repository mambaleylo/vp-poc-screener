"""Классика's filters (the user: "давай дальше эксперименты, фильтры"): the trades of the deployed rule (v0.99.777, B) with their
signal's features (CFL_FNAMES: the volatility, RSI, the range position, the volume, the fall before, BTC, the funding, the hour,
the day, the family) -> for each feature its quintiles' bars from 2023–2024's trades only; R / WR / n per quintile in 2023–24
(where the bars came from) and 2025–26 (never seen by them); a filter is kept only if dropping its worst quintile lifts the mean
R in BOTH periods. usage (tools/winrate): python3 cfl_filt.py  (run_cflvar.sh's environment)"""
import os, sys, json, numpy as np
sys.argv = ["x"]
exec(open("cfl_var.py").read().rsplit('if __name__ == "__main__":', 1)[0])
B = "dr14+c210+cap30+s0.5t6+ctf4"
p = dict(BASE)
for part in B.split("+"): p = merge(p, VARS[part])
L = build(p); I = np.array([x["i"] for x in L]); R = np.array([x["r"] for x in L]); T0 = np.array([x["t0"] for x in L])
A = T0 < ts(2025); Bm = ~A
print(f"сделок {len(L)}: 2023–24 {A.sum()} ({R[A].mean():+.2f}R, WR {(R[A] > 0).mean() * 100:.0f}%), 2025–26 {Bm.sum()} ({R[Bm].mean():+.2f}R, WR {(R[Bm] > 0).mean() * 100:.0f}%)", flush=True)
out = {}
for k, nm in enumerate(E3.FNAMES):
    if nm in ("side",): continue
    v = Dd["F"][I, k].astype(float)
    if nm == "fam":
        rows = []
        for f in sorted(set(v[np.isfinite(v)].astype(int))):
            m = v == f; rows.append((E3.FAMS[f], int((m & A).sum()), R[m & A].mean() if (m & A).any() else np.nan, int((m & Bm).sum()), R[m & Bm].mean() if (m & Bm).any() else np.nan))
        print("семейства:", "; ".join(f"{a} {b}:{c:+.2f}/{d}:{e:+.2f}" for a, b, c, d, e in rows), flush=True); continue
    ok = np.isfinite(v)
    if ok.sum() < 0.8 * len(v) or len(np.unique(v[ok & A])) < 5: continue
    q = np.quantile(v[ok & A], [0.2, 0.4, 0.6, 0.8]); b = np.digitize(v, q)
    ra = [R[(b == j) & A & ok].mean() for j in range(5)]; rb = [R[(b == j) & Bm & ok].mean() for j in range(5)]
    best = None
    for j, side in ((0, "low"), (4, "high")):   # drop the worst end quintile (by 2023–24)
        keep = ok & (b != j)
        ga, gb = R[keep & A].mean() - R[A].mean(), R[keep & Bm].mean() - R[Bm].mean()
        if best is None or ga > best[1]: best = (side, ga, gb, float(q[0] if j == 0 else q[3]), int((~keep & Bm).sum()))
    out[nm] = {"q": [float(x) for x in q], "r2324": [round(float(x), 2) for x in ra], "r2526": [round(float(x), 2) for x in rb], "drop": best}
    flag = "✔" if best[1] > 0.05 and best[2] > 0.05 else " "
    print(f"{flag} {nm:8s} квинтили 23–24: {' '.join(f'{x:+.2f}' for x in ra)} | 25–26: {' '.join(f'{x:+.2f}' for x in rb)} | без {'нижней' if best[0] == 'low' else 'верхней'} пятой (порог {best[3]:.4g}): "
          f"23–24 {best[1]:+.2f}R, 25–26 {best[2]:+.2f}R", flush=True)
json.dump(out, open(f"{ST}/wf/cfl_filt.json", "w"), indent=1)
print("cfl filt done", flush=True)
