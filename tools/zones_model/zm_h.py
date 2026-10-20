"""Strong zones — a harness on the deployed scheme's walk-forward scores (zm_sel.py), the label grid G_<buffer>_R<take>
(the zone limit, the stop `buffer` daily ATR past the zone, the take R): one zone trade per coin & side until it ends."""
import sys, numpy as np, pandas as pd, datetime as dt
from mk import df, ts
from common import D
LABS = [f"G_{b}_R{t}" for b in ("0.75", "1.0", "1.5", "2.0") for t in ("1.5", "2.0", "3.0", "4.0", "6.0")]
d = df(LABS + [l + "_h" for l in LABS])
S = np.load(f"{D}/zm_sel.npz"); SC, T95, T85 = S["sc"], S["t95"], S["t85"]
T = d.t.values.astype(np.int64); SYM = d.sym.values; SIDE = np.where(d.side_s.astype(str).values == "long", 1, -1)
YR = np.minimum(np.array([dt.datetime.fromtimestamp(int(t), dt.timezone.utc).year for t in T]), 2025)
def cand(q, mask=None):
    m = (SC >= (T95 if q == 0.95 else T85)) & ~np.isnan(SC) & (T >= ts(2022))
    if mask is not None: m &= mask
    return np.where(m)[0]
def replay(idx, lab):
    R = d[lab].values.astype(float); H = np.nan_to_num(d[lab + "_h"].values.astype(float), nan=24.0)
    o = idx[np.lexsort((-SC[idx], T[idx]))]
    busy, act, out = {}, [], []
    for i in o:
        if R[i] != R[i]: continue
        t = T[i]; k = (SYM[i], SIDE[i])
        if busy.get(k, 0) > t: continue
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == SIDE[i]) >= 12: continue
        end = t + int(H[i]) * 3600; busy[k] = end; act.append((end, SIDE[i])); out.append((int(t), int(end), float(R[i]), int(SIDE[i]), int(i)))
    return out
rng = np.random.default_rng(5)
def pain(tr, target, grid, nb=250):
    bl = {}
    for n_, x in enumerate(tr): bl.setdefault(x[0] // (30 * 86400), []).append(n_)
    bl = list(bl.values()); B = []
    for _ in range(nb):
        ev, base = [], 0
        for z, b in enumerate(rng.choice(len(bl), len(bl))):
            t0 = min(tr[n_][0] for n_ in bl[b])
            for n_ in bl[b]: ev += [(base + tr[n_][0] - t0, 0, n_, (z, n_)), (base + tr[n_][1] - t0, 1, n_, (z, n_))]
            base += 40 * 86400
        B.append(sorted(ev, key=lambda e: (e[0], -e[1])))
    best = None
    for f in grid:
        xs, ds = [], []
        for ev in B:
            eq, peak, dd, risk = 1.0, 1.0, 0.0, {}
            for _, k, n_, u in ev:
                if k == 0: risk[u] = eq * f
                else:
                    eq += risk.pop(u) * tr[n_][2]; peak = max(peak, eq); dd = max(dd, 1 - eq / peak)
                    if eq <= 0.02: eq, dd = 0.0, 1.0; break
            xs.append(eq); ds.append(dd)
        if np.quantile(ds, .9) <= target: best = (f, float(np.median(xs)), float(np.median(ds)))
        else: break
    return best
def line(nm, tr, q):
    r = np.array([x[2] for x in tr]); t = np.array([x[0] for x in tr]); run = w = 0
    for x in sorted(tr, key=lambda x: x[1]): run = run + 1 if x[2] < 0 else 0; w = max(w, run)
    yrs = " ".join(f"{r[(t >= ts(y)) & (t < ts(y + 1))].mean():+.2f}" for y in (2022, 2023, 2024, 2025, 2026))
    b = pain(tr, 0.45 if q == 0.95 else 0.50, (0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04) if q == 0.95 else (0.001, 0.002, 0.003, 0.005, 0.0075, 0.01))
    print(f"{nm:40s} {len(r):5d} {r.mean():+.3f} WR {np.mean(r > 0)*100:3.0f}% подряд {w:2d} | {yrs} | " + (f"{b[0]*100:.2f}%: x{b[1]:.1f} (обычная {b[2]*100:.0f}%)" if b else "—"), flush=True)
