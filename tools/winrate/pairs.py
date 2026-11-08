"""Hypothesis 7 (the user picked it): market-neutral long / short of the 127 bot coins. Every day at 00:00 UTC: each coin's own move
over L hours less beta x BTC's (beta: the last 30 days' hourly regression); the k lowest and the k highest -> mean-reversion (long the
lowest, short the highest) or momentum (the other way); each leg sized to an equal risk (1 / its 30-day hourly vol), the longs' and
the shorts' risks equal (the market's move cancels); held H hours; the fee 0.1% a leg in + out, the funding as paid. -> the day's
return per unit of risk; by 2023–24 vs 2025–26, and in Классика's quiet (cfl_idle's: no Классика trade open, its last entry >= 14 days
before). usage: python3 pairs.py"""
import os, json, calendar, numpy as np, itertools
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
sp = json.load(open("lv/split.json")); COINS = sorted(sp["bot"])
ts = lambda y, m=1, d=1: calendar.timegm((y, m, d, 0, 0, 0)); A0, MID, END = ts(2023), ts(2025), ts(2026, 10)
HR = np.arange(ts(2022, 10), END, 3600); n = len(HR)
def close_of(sym):
    a = np.loadtxt(f"{ST}/data/1h/{sym}.csv.gz", delimiter=",", ndmin=2); t = a[:, 0].astype(np.int64); c = a[:, 4]
    out = np.full(n, np.nan); j = np.searchsorted(t, HR); ok = (j < len(t)) & (t[np.minimum(j, len(t) - 1)] == HR); out[ok] = c[j[ok]]
    return out
def fund_of(sym):
    fn = f"{ST}/data/funding/{sym}.csv"; out = np.zeros(n)
    if os.path.exists(fn):
        f = np.loadtxt(fn, delimiter=",", ndmin=2)
        if len(f): k = np.searchsorted(HR, f[:, 0].astype(np.int64)); ok = k < n; np.add.at(out, k[ok], f[ok, 1])
    return out
BTC = close_of("BTCUSDT"); C = np.vstack([close_of(s) for s in COINS]); FU = np.vstack([fund_of(s) for s in COINS])
R1 = np.full_like(C, np.nan); R1[:, 1:] = np.log(C[:, 1:] / C[:, :-1]); B1 = np.full(n, np.nan); B1[1:] = np.log(BTC[1:] / BTC[:-1])
print("монет", len(COINS), "часов", n, flush=True)
# Классика's quiet days (cfl_idle_R_22.npz holds the quiet events; the quiet hours = recomputed from the deployed list)
QUIET = None
try:
    L = json.load(open(f"{ST}/wf/cfl_var_dr14+c210+cap30+s0.5t6+ctf4+s0.4t8+q995+fpos90+fatrh+fde50.json"))
    E0 = np.array(sorted(x["t0"] for x in L)); SP = sorted((x["t0"], x["t1"]) for x in L)
    def quiet(t):
        k = np.searchsorted(E0, t, side="right") - 1
        if k >= 0 and t - E0[k] < 14 * 86400: return False
        return not any(a <= t < b for a, b in SP[max(0, k - 40):k + 1])
    QUIET = quiet
except Exception as e:
    print("тишина Классики не загрузилась:", e)
days = [d for d in range(A0, END - 5 * 86400, 86400)]
PRE = {}   # day -> (beta, vol) of every coin over the 30 days before (once: they do not depend on L / H / k / the way)
for d in days:
    i = int((d - HR[0]) // 3600)
    if i - 720 < 0: continue
    x = B1[i - 720:i]; Y = R1[:, i - 720:i]; m = np.isfinite(Y) & np.isfinite(x)[None, :]
    cnt = m.sum(axis=1); xm = np.where(m, x[None, :], 0.0); ym = np.where(m, Y, 0.0)
    mx = xm.sum(axis=1) / np.maximum(cnt, 1); my = ym.sum(axis=1) / np.maximum(cnt, 1)
    cov = ((xm - mx[:, None]) * (ym - my[:, None]) * m).sum(axis=1) / np.maximum(cnt - 1, 1)
    vx = (((xm - mx[:, None]) ** 2) * m).sum(axis=1) / np.maximum(cnt - 1, 1); vy = (((ym - my[:, None]) ** 2) * m).sum(axis=1) / np.maximum(cnt - 1, 1)
    beta = cov / np.maximum(vx, 1e-12); vol = np.sqrt(vy); bad = cnt < 500; beta[bad] = np.nan; vol[bad] = np.nan
    PRE[d] = (beta, vol)
print("наклоны к BTC посчитаны", flush=True)
res = []
for Lh, Hh, k, way in itertools.product((24, 72, 168), (24, 48, 96), (3, 6), ("возврат", "инерция")):
    rows = []
    for d in days:
        i = int((d - HR[0]) // 3600)
        if d not in PRE or i + Hh >= n: continue
        beta, vol = PRE[d]
        mv = np.log(C[:, i] / C[:, i - Lh]) - beta * np.log(BTC[i] / BTC[i - Lh])
        mv[~np.isfinite(C[:, i + Hh])] = np.nan
        ok = np.isfinite(mv) & np.isfinite(vol) & (vol > 0)
        if ok.sum() < 30: continue
        idx = np.where(ok)[0]; o = idx[np.argsort(mv[idx])]; lo, hi = o[:k], o[-k:]
        longs, shorts = (lo, hi) if way == "возврат" else (hi, lo)
        def leg(cs, s):   # the leg's return per unit of risk (each coin's weight 1/vol, the leg's total risk 1)
            wt = 1 / vol[cs]; wt = wt / wt.sum()
            r = s * (C[cs, i + Hh] / C[cs, i] - 1) - 0.002 - s * FU[cs, i:i + Hh].sum(axis=1)
            return float((wt * r / (vol[cs] * np.sqrt(Hh))).sum())
        rows.append((d, 0.5 * (leg(longs, 1) + leg(shorts, -1))))
    rows = np.array(rows)
    if not len(rows): continue
    t, r = rows[:, 0], rows[:, 1]; a, b = t < MID, t >= MID
    q = np.array([QUIET(int(x)) for x in t]) if QUIET else np.zeros(len(t), bool)
    o = {"L": Lh, "H": Hh, "k": k, "way": way, "a": [int(a.sum()), round(float(r[a].mean()), 4), round(float(r[a].mean() / r[a].std() * np.sqrt(365 / (Hh / 24))), 2)],
         "b": [int(b.sum()), round(float(r[b].mean()), 4), round(float(r[b].mean() / r[b].std() * np.sqrt(365 / (Hh / 24))), 2)],
         "quiet": [int(q.sum()), round(float(r[q].mean()), 4) if q.any() else None]}
    res.append(o)
    print(f"{way:8s} L{Lh:3d}ч H{Hh:2d}ч k{k} | 2023–24: средн. {o['a'][1]:+.4f} (Шарп {o['a'][2]:+.2f}) | 2025–26: {o['b'][1]:+.4f} (Шарп {o['b'][2]:+.2f}) | в тишину Классики: {o['quiet']}", flush=True)
json.dump(res, open(f"{ST}/wf/pairs.json", "w"), indent=1)
print("pairs done", flush=True)
