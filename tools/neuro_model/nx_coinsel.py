"""auto-selection of coins: a coin trades in year Y only if the model's trades on it in the years before (out of
sample there too) were good — compared with trading every coin"""
import sys, json, numpy as np
ARGV = sys.argv[1:]
from common import D
from mk import ts
fn, q = ARGV[0], ARGV[1]
TR = json.load(open(fn))[q]
years = sorted(int(y) for y in TR)
by = {y: TR[str(y)] for y in years}   # [end, r, sym, side, t]
def stats(rows, wk):
    if not rows:
        return "n=0"
    rs = np.array([r[1] for r in sorted(rows)]); cum = np.cumsum(rs)
    dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], cum])) - np.concatenate([[0], cum])))
    return f"{rs.mean():+.2f}R×{len(rs) / wk:.1f}/нед Σ{rs.sum():.0f} dd{dd:.0f}"
def coin_stats(rows):
    d = {}
    for r in rows:
        d.setdefault(r[2], []).append(r[1])
    return {k: (len(v), float(np.mean(v)), float(np.sum(v))) for k, v in d.items()}
rules = {
    "все монеты": lambda prev, allp: None,
    "прошлый год >0 (n≥5)": lambda prev, allp: {k for k, (n, a, s) in prev.items() if n >= 5 and a > 0},
    "прошлый год ≥+0.1R (n≥8)": lambda prev, allp: {k for k, (n, a, s) in prev.items() if n >= 8 and a >= 0.1},
    "топ-30 прошлого года по ΣR": lambda prev, allp: {k for k, _ in sorted(prev.items(), key=lambda x: -x[1][2])[:30]},
    "все прошлые годы >0 (n≥10)": lambda prev, allp: {k for k, (n, a, s) in allp.items() if n >= 10 and a > 0},
    "все прошлые годы ≥+0.1R (n≥10)": lambda prev, allp: {k for k, (n, a, s) in allp.items() if n >= 10 and a >= 0.1},
}
for name, f in rules.items():
    line = []
    for y in years[1:]:
        prev = coin_stats(by[y - 1])
        allp = coin_stats([r for yy in years if yy < y for r in by[yy]])
        keep = f(prev, allp)
        rows = [r for r in by[y] if keep is None or r[2] in keep]
        wk = ((ts(y + 1) if y < 2025 else ts(2026, 10)) - ts(y)) / (7 * 86400)
        line.append(f"{y}: {stats(rows, wk)}" + (f" [{len(keep)} мон.]" if keep is not None else ""))
    print(f"{name:32s} " + " | ".join(line))
