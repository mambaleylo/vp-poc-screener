import json, numpy as np
rr = [r for r in json.load(open("gh_dlm.json")) if r]
R = np.array([r["R"] for r in rr]); Y = np.array([r["y"] for r in rr])
keys = [k for k in rr[0] if k not in ("R", "te", "sym", "d", "y")]
res = []
for k in keys:
    x = np.array([r[k] for r in rr], float)
    if len(set(np.round(x[np.isfinite(x)], 6))) <= 3:
        g = [(f"={v:g}", x == v) for v in sorted(set(x[np.isfinite(x)]))]
    else:
        q = np.nanquantile(x, [0.2, 0.4, 0.6, 0.8]); g = [("q1", x <= q[0]), ("q2", (x > q[0]) & (x <= q[1])), ("q3", (x > q[1]) & (x <= q[2])), ("q4", (x > q[2]) & (x <= q[3])), ("q5", x > q[3])]
    lo, hi = g[0][1], g[-1][1]; d = R[hi].mean() - R[lo].mean()
    yd = [R[hi & (Y == y)].mean() - R[lo & (Y == y)].mean() for y in range(2022, 2027) if (hi & (Y == y)).sum() >= 15 and (lo & (Y == y)).sum() >= 15]
    cons = np.mean(np.sign(yd) == np.sign(d)) if yd else 0
    res.append((abs(d) * cons, k, d, cons, len(yd), " · ".join(f"{a} {R[m].mean():+.2f}" for a, m in g), " ".join(f"{v:+.2f}" for v in yd)))
res.sort(reverse=True)
print(f"⚡ пул {len(rr)} средний {R.mean():+.3f}R")
for sc, k, d, cons, ny, txt, yy in res[:14]:
    print(f"{k:11s} {d:+.2f}R знак {cons*100:3.0f}% из {ny} лет [{yy}] | {txt}")
