"""the account size where the bundle's trades start to move their coins (the user: "при каком балансе… начнутся проблемы с
проскальзыванием"): every trade of 2025-2026 (⚡ filled orders _clr, P/R / SMC / EMA / HTF from the bot's list): its position
per $1 of the balance = the module's risk / the stop's distance; the coin's hourly turnover ($, the median of the 24 h before
the trade, the lab-store's Binance 1h candles); the balance at which the position is X% of an hour's turnover (a market stop /
a market entry of that size moves the price; a limit that big fills only partly) — the share of trades over it by balance;
and Binance's leverage brackets (brackets.json, the bot's own download): the balance where the position leaves the top-leverage
tier and where it hits the coin's largest allowed position. usage: ALLSUF=_clr liq_cap.py"""
import sys, os, json, bisect, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X, money_params as MP
RK = MP.rk(emx=3.0); A0 = M.ts(2025)
BR = json.load(open(f"{M.ST}/brackets.json"))
V1 = {}
def vol1h(sym, t):
    if sym not in V1:
        fn = os.path.join(M.ST, "data", "1h", f"{sym}.csv.gz")
        if not os.path.exists(fn): V1[sym] = None
        else:
            a = np.loadtxt(fn, delimiter=",", ndmin=2, usecols=(0, 5)); V1[sym] = (a[:, 0].astype(np.int64), a[:, 1])
    if V1[sym] is None: return None
    T, Q = V1[sym]; i = bisect.bisect_right(T, t - 3600)
    return float(np.median(Q[max(0, i - 24):i])) if i > 0 else None
rows = []
for o in MA2.orders():
    if o["filled"] and o["t"] >= A0: rows.append(("⚡", o["sym"], o["t"], RK["dlm"] / 100 / o["st"]))
for v in M.build("base"):
    if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"} and v["t0"] >= A0: rows.append((v["mod"], v["sym"], v["t0"], RK[v["mod"]] / 100 / v["st"]))
print(f"риск модулей, %: {RK}; сделок 2025-26: {len(rows)}", flush=True)
mods = sorted({r[0] for r in rows}); out = {}
nb = np.array([r[3] for r in rows]); vv = np.array([vol1h(r[1], r[2]) or np.nan for r in rows]); md = np.array([r[0] for r in rows]); syms = [r[1] for r in rows]
ok = np.isfinite(vv) & (vv > 0)
print(f"позиция на $1 баланса: медиана ${np.median(nb):.2f}, 90% ${np.percentile(nb, 90):.2f}; часовой оборот монеты: медиана ${np.median(vv[ok]) / 1e6:.1f}M, "
      f"10% худших ${np.percentile(vv[ok], 10) / 1e6:.2f}M", flush=True)
print("\nбаланс | доля сделок, где позиция > 1% часового оборота | > 5% | > 20% (и так по модулям для 5%)", flush=True)
for B in (1e3, 3e3, 1e4, 3e4, 1e5, 3e5, 1e6, 3e6):
    sh = (nb * B / vv)[ok]
    per = " · ".join(f"{m} {((nb * B / vv)[ok & (md == m)] > 0.05).mean() * 100:.0f}%" for m in mods)
    print(f"${B:,.0f} | {(sh > 0.01).mean() * 100:.0f}% | {(sh > 0.05).mean() * 100:.0f}% | {(sh > 0.20).mean() * 100:.0f}% | 5%: {per}", flush=True)
def br(sym):
    b = BR.get(sym)
    return sorted(b) if b else None
top = np.array([(br(s)[0][0] if br(s) else np.nan) for s in syms]); cap = np.array([(br(s)[-1][0] if br(s) else np.nan) for s in syms])
lev10 = np.array([next((c for c, l, _ in br(s) if l <= 10), np.nan) if br(s) else np.nan for s in syms])
ob = np.isfinite(top)
print("\nбаланс | позиция больше первой ступени плеча Binance (плечо ниже максимума) | плечо ≤ 10x | больше максимальной позиции монеты", flush=True)
for B in (1e3, 3e3, 1e4, 3e4, 1e5, 3e5, 1e6):
    p = nb * B
    print(f"${B:,.0f} | {(p[ob] > top[ob]).mean() * 100:.0f}% | {(p[ob] > np.nan_to_num(lev10[ob], nan=np.inf)).mean() * 100:.0f}% | {(p[ob] > cap[ob]).mean() * 100:.0f}%", flush=True)
print("liq cap done", flush=True)
