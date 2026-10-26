"""'разгон': $10, one trade at a time with ALL the balance as margin at the max leverage, withdraw everything above $n;
a bust (the balance < $1, i.e. below what a min order needs) -> a new $10 deposit. The bundle's trades (⚡ / P/R / SMC /
EMA rows of the money sim, R incl. fees / funding / slippage as there), taken first-come while flat.
Per trade: balance x (1 + lev x R x ST), R x ST = the price move at the exit; lev = the largest whole leverage whose
liquidation (1/lev - 0.5% maintenance - 0.55% fees/slip, the sim's isolated rule) lies beyond the emergency stop x1.5
(BUF), capped at LCAP -> no liquidation before the exchange stop; a gap past it = the R as walked (the stop's)."""
import sys, numpy as np
exec(open("port_be5d.py").read())
t0, t1, r_, st_, sth, buf, md, ci, wg, tbr = A_.T; md = md.astype(int)
NM = {0: "⚡", 1: "P/R", 2: "SMC", 3: "EMA"}
print("rows", len(t0), "from", np.datetime64(int(t0.min()), "s"), "to", np.datetime64(int(t0.max()), "s"), flush=True)
def sim(a, b, n, lcap, mods=(0, 1, 2, 3), dep=10.0, fixed_lev=0):
    bal = dep; deps = dep; wd = 0.0; busy = 0.0; nt = 0; busts = 0; lev_used = []
    for j in range(np.searchsorted(t0, a), len(t0)):
        if t0[j] >= b: break
        if t0[j] < busy or md[j] not in mods: continue
        lev = fixed_lev or min(lcap, np.floor(1.0 / (buf[j] * sth[j] + 0.0105)))
        if lev < 1: continue
        g = lev * r_[j] * st_[j]
        bal *= max(0.0, 1 + g); busy = t1[j]; nt += 1; lev_used.append(lev)
        if bal > n: wd += bal - n; bal = n
        if bal < 1.0:
            busts += 1; bal = dep; deps += dep
    return wd, deps, bal, nt, busts, np.mean(lev_used) if lev_used else 0
starts = [ts(2022, m) for m in range(1, 13)] + [ts(2023, m) for m in range(1, 13)] + [ts(2024, m) for m in range(1, 13)] + [ts(2025, m) for m in range(1, 11)]
for lcap in (20, 50, 125):
    for n in (20, 50, 100, 300, 1000, 1e12):
        res = [sim(s, s + 365 * 86400, n, lcap) for s in starts]
        net = np.array([w + b - d for w, d, b, *_ in res]); wd = np.array([r[0] for r in res]); dp = np.array([r[1] for r in res])
        bu = np.array([r[4] for r in res]); nt = np.array([r[3] for r in res])
        print(f"плечо до x{lcap:<3d} вывод сверх ${n if n < 1e11 else 'никогда':<7} | за 12 мес: выведено медиана ${np.median(wd):>9,.0f} (10% ${np.percentile(wd, 10):,.0f}, 90% ${np.percentile(wd, 90):,.0f}) "
              f"внесено медиана ${np.median(dp):,.0f} итог(вывод+остаток-внесено) медиана ${np.median(net):>9,.0f}, в минусе {np.mean(net < 0)*100:.0f}% окон | сделок {np.median(nt):.0f} сливов {np.median(bu):.0f} ср.плечо x{np.mean([r[5] for r in res]):.0f}", flush=True)
l = sim(ts(2025, 10), ts(2026, 10), 1e12, 20); print("last 12m, x20, no withdraw:", l)
