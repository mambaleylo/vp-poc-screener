"""walk-forward: for each test year, from the past years only — the feature, its terciles and the favourable side;
the weight x1.25 in the good tercile, x0.85 in the bad one; the test year's weighted R vs plain"""
import json, numpy as np
rows = json.load(open("gh_states.json"))
keys = [k for k in rows[0] if k not in ("mod", "R", "y", "s", "te")]
UP, DN = 1.25, 0.85
def pick(rr, R, Y, fixed=None):
    best = None
    for k in ([fixed] if fixed else keys):
        x = np.array([r.get(k, np.nan) for r in rr], float)
        if not np.isfinite(x).any() or np.nanstd(x) == 0: continue
        vals = sorted(set(x[np.isfinite(x)]))
        if len(vals) <= 3: cuts = ("flag", vals[0], vals[-1])
        else: cuts = ("q",) + tuple(np.nanquantile(x, [1 / 3, 2 / 3]))
        lo, hi = (x == cuts[1], x == cuts[2]) if cuts[0] == "flag" else (x <= cuts[1], x > cuts[2])
        if lo.sum() < 30 or hi.sum() < 30: continue
        d = R[hi].mean() - R[lo].mean()
        yd = [R[hi & (Y == y)].mean() - R[lo & (Y == y)].mean() for y in sorted(set(Y)) if (hi & (Y == y)).sum() >= 8 and (lo & (Y == y)).sum() >= 8]
        cons = np.mean(np.sign(yd) == np.sign(d)) if yd else 0
        sc = abs(d) * cons * (len(yd) >= 2)
        if best is None or sc > best[0]: best = (sc, k, cuts, np.sign(d))
    return best
def weights(rr, b):
    _, k, cuts, sg = b; x = np.array([r.get(k, np.nan) for r in rr], float)
    lo, hi = (x == cuts[1], x == cuts[2]) if cuts[0] == "flag" else (x <= cuts[1], x > cuts[2])
    w = np.ones(len(rr)); good, bad = (hi, lo) if sg > 0 else (lo, hi)
    w[good] = UP; w[bad] = DN; return w
for mod in ("prv", "smc", "emx"):
    rr = [r for r in rows if r["mod"] == mod]; R = np.array([r["R"] for r in rr]); Y = np.array([r["y"] for r in rr])
    print(f"== {mod}")
    tot_p = tot_w = 0
    for ty in (2024, 2025, 2026):
        tr = Y < ty; te = Y == ty
        b = pick([r for r, f in zip(rr, tr) if f], R[tr], Y[tr])
        if not b: continue
        w = weights([r for r, f in zip(rr, te) if f], b)
        p, q = R[te].mean(), (w * R[te]).sum() / w.sum()
        tot_p += R[te].sum(); tot_w += (w * R[te]).sum() / w.mean()
        print(f"  {ty}: {b[1]:10s} ({'+' if b[3] > 0 else '-'}) plain {p:+.3f}R  weighted {q:+.3f}R  ({te.sum()} trades)")
    print(f"  total R plain {tot_p:+.1f}  weighted(same mean weight) {tot_w:+.1f}")
