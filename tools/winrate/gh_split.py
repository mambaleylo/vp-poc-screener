import json, numpy as np
rows = json.load(open("gh_states.json"))
keys = [k for k in rows[0] if k not in ("mod", "R", "y")]
for mod in ("dlm", "prv", "smc", "emx"):
    rr = [r for r in rows if r["mod"] == mod]; R = np.array([r["R"] for r in rr]); Y = np.array([r["y"] for r in rr])
    out = []
    for k in keys:
        x = np.array([r.get(k, np.nan) for r in rr], float)
        if np.nanstd(x) == 0: continue
        if len(set(np.round(x[np.isfinite(x)], 6))) <= 3:   # a sign / flag: groups by value
            groups = [(f"={v:g}", x == v) for v in sorted(set(x[np.isfinite(x)]))]
        else:
            q1, q2 = np.nanquantile(x, [1 / 3, 2 / 3]); groups = [("низ", x <= q1), ("сер", (x > q1) & (x <= q2)), ("верх", x > q2)]
        if len(groups) < 2: continue
        lo, hi = groups[0][1], groups[-1][1]
        if lo.sum() < 40 or hi.sum() < 40: continue
        d = R[hi].mean() - R[lo].mean()
        yd = [R[hi & (Y == y)].mean() - R[lo & (Y == y)].mean() for y in sorted(set(Y)) if (hi & (Y == y)).sum() >= 10 and (lo & (Y == y)).sum() >= 10]
        cons = np.mean(np.sign(yd) == np.sign(d)) if yd else 0
        out.append((abs(d) * cons, k, d, cons, len(yd), " · ".join(f"{g} {R[m].mean():+.2f} ({m.sum()})" for g, m in groups)))
    out.sort(reverse=True)
    print(f"== {mod} ({len(rr)}), средний {R.mean():+.3f}R")
    for sc, k, d, cons, ny, txt in out[:8]:
        print(f"  {k:12s} разница {d:+.2f}R, тот же знак в {cons*100:.0f}% из {ny} лет | {txt}")
