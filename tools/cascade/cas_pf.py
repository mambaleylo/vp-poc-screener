import numpy as np, json
from cas_h import trades, prv, X, SD, ts
from nx_h import rng
CN = ["s", "rng", "prior", "since_opp", "exc", "move24", "width", "b24", "atrp"]
tr = trades("sw_t2_48", 0.995); tr = [x for x in tr if x[0] >= ts(2023)]
rows = np.array([x[4] for x in tr]); R = np.array([x[2] for x in tr])
print("что выбирает модель (медианы): выбранные vs все события")
for k, c in enumerate(CN[1:], 1):
    print(f"  {c:10s} шорт {np.median(X[rows[SD[rows] < 0], k]):7.2f} / {np.median(X[SD < 0, k]):7.2f}   лонг {np.median(X[rows[SD[rows] > 0], k]):7.2f} / {np.median(X[SD > 0, k]):7.2f}")
sh = rows[SD[rows] < 0]
print(f"  шорты: памп-затухание (prior>=24 и exc>=4) {np.mean((X[sh,2]>=24)&(X[sh,4]>=4)):.0%}, пробой-отбой (since_opp<=6) {np.mean(X[sh,3]<=6):.0%}")
for nm, m in (("памп-затухание", (X[sh,2]>=24)&(X[sh,4]>=4)), ("отбой <=6", X[sh,3]<=6), ("прочие", ~(((X[sh,2]>=24)&(X[sh,4]>=4)) | (X[sh,3]<=6)))):
    rr = R[np.isin(rows, sh[m])]; print(f"    {nm}: {len(rr)} сделок, {rr.mean():+.2f}R WR {np.mean(rr>0):.0%}")
P = prv()
def sim(tr, f, nb=300):
    bl = {}
    for n_, x in enumerate(tr): bl.setdefault(x[0] // (30 * 86400), []).append(n_)
    bl = list(bl.values()); xs, ds = [], []
    for _ in range(nb):
        ev, base = [], 0
        for z, b in enumerate(rng.choice(len(bl), len(bl))):
            t0 = min(tr[n_][0] for n_ in bl[b])
            for n_ in bl[b]: ev += [(base + tr[n_][0] - t0, 0, n_, (z, n_)), (base + tr[n_][1] - t0, 1, n_, (z, n_))]
            base += 40 * 86400
        ev.sort(key=lambda e: (e[0], -e[1])); eq, peak, dd, risk = 1.0, 1.0, 0.0, {}
        for _, k, n_, u in ev:
            if k == 0: risk[u] = eq * tr[n_][5]
            else:
                eq += risk.pop(u) * tr[n_][2]; peak = max(peak, eq); dd = max(dd, 1 - eq / peak)
                if eq <= 0.02: eq, dd = 0.0, 1.0; break
        xs.append(eq); ds.append(dd)
    return np.median(xs), np.quantile(ds, .9)
print("\nP/R 4% + каскад w% (2023–26, 1 раз из 10 просадка):")
for w in (0, 0.005, 0.01, 0.015, 0.02):
    comb = [x + (0.04,) for x in P] + ([x + (w,) for x in tr] if w else [])
    comb.sort(); mx, dd = sim(comb, 0)
    print(f"  каскад {w*100:.1f}%: x{mx:.0f}, просадка 1/10 {dd*100:.0f}%")
for w in (0.06, 0.08):
    mx, dd = sim(sorted([x + (w,) for x in P]), 0); print(f"  только P/R {w*100:.0f}%: x{mx:.0f}, просадка 1/10 {dd*100:.0f}%")
