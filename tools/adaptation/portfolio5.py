"""P/R + EMA (v0.99.664: the entry 0.2 daily ATR past the EMA) + 📈 breakout + 🌊 cascade on the bot's backtest lists, 2023-01 .. 2026-09:
the risk split at a 1-in-10 drawdown limit, and what $100 becomes in 1 / 6 / 12 months (block bootstrap by month)"""
import json, itertools, numpy as np, datetime as dt
bt = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))
T0, T1 = int(dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc).timestamp()), int(dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc).timestamp())
MODS = ("prv", "emx", "rbx", "cas"); NAME = {"prv": "P/R", "emx": "EMA", "rbx": "Пробой", "cas": "Каскад"}
tr = sorted((t["t"], t["x"], t["r"], m) for m in MODS for t in bt[m] if T0 <= t["t"] < T1 and t.get("r") is not None)
MI = {m: k for k, m in enumerate(MODS)}
print("сделок:", {NAME[m]: sum(1 for x in tr if x[3] == m) for m in MODS})
ym = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m")
months = sorted({ym(x[1]) for x in tr})
mon = {m: np.array([sum(x[2] for x in tr if x[3] == m and ym(x[1]) == k) for k in months]) for m in MODS}
print("корреляция месяцев:", {f"{NAME[a]}–{NAME[b]}": round(float(np.corrcoef(mon[a], mon[b])[0, 1]), 2) for a, b in itertools.combinations(MODS, 2)})
blocks = {}
for i, x in enumerate(tr): blocks.setdefault(ym(x[0]), []).append(i)
bl = list(blocks.values())
R = np.array([x[2] for x in tr]); M = np.array([MI[x[3]] for x in tr])
rng = np.random.default_rng(11)
def boot(nm):
    ev, base = [], 0
    for z, b in enumerate(rng.choice(len(bl), nm)):
        t0 = min(tr[i][0] for i in bl[b])
        for i in bl[b]: ev += [(base + tr[i][0] - t0, 0, i, z), (base + tr[i][1] - t0, 1, i, z)]
        base += 31 * 86400
    ev.sort(key=lambda e: (e[0], -e[1]))
    return np.array([[e[1], e[2], e[3]] for e in ev], dtype=np.int64)
from numba import njit
@njit(cache=True)
def sim(ev, R, M, f, nz):
    eq, peak, dd = 1.0, 1.0, 0.0
    risk = np.zeros((nz, len(R)))
    for k in range(len(ev)):
        typ, i, z = ev[k, 0], ev[k, 1], ev[k, 2]
        if typ == 0: risk[z, i] = eq * f[M[i]]
        else:
            eq += risk[z, i] * R[i]; peak = max(peak, eq); dd = max(dd, 1 - eq / peak)
            if eq <= 0.02: return 0.0, 1.0
    return eq, dd
NM = len(bl)
B = [boot(NM) for _ in range(200)]
def stat(f, BB=B, nz=NM):
    fa = np.array([f[m] for m in MODS]); rr = [sim(b, R, M, fa, nz) for b in BB]
    xs = np.array([a[0] for a in rr]); ds = np.array([a[1] for a in rr])
    return float(np.median(xs)), float(np.median(ds)), float(np.quantile(ds, .9))
G = {"prv": (0.03, 0.04, 0.06), "emx": (0.02, 0.03, 0.04), "rbx": (0.005, 0.01, 0.015), "cas": (0.0, 0.01, 0.015, 0.02)}
res = []
for combo in itertools.product(*[G[m] for m in MODS]):
    f = dict(zip(MODS, combo)); x, d50, d90 = stat(f); res.append((combo, x, d50, d90))
print(f"\nриск {' / '.join(NAME[m] for m in MODS)} -> рост за {NM} мес (медиана) | просадка обычная / 1 раз из 10")
best = {}
for lim in (0.30, 0.40):
    ok = sorted([r for r in res if r[3] <= lim], key=lambda r: -r[1])
    print(f"-- просадка 1 из 10 не больше {lim:.0%}:")
    for c, x, d50, d90 in ok[:4]:
        print(f"   {' / '.join(f'{v*100:g}%' for v in c)}: x{x:,.0f} (~{(x ** (1 / NM) - 1) * 100:+.1f}%/мес) | {d50*100:.0f}% / {d90*100:.0f}%")
    if ok: best[lim] = ok[0]
    nc = [r for r in ok if r[0][3] == 0]
    if nc: print(f"   (без каскада лучшее: {' / '.join(f'{v*100:g}%' for v in nc[0][0])}: x{nc[0][1]:,.0f}, ~{(nc[0][1] ** (1 / NM) - 1) * 100:+.1f}%/мес)")
for lim, (c, x, d50, d90) in best.items():
    f = dict(zip(MODS, c)); fa = np.array(c)
    print(f"\n$100 при риске {' / '.join(f'{v*100:g}%' for v in c)} (просадка 1/10 ≤{lim:.0%}):")
    for nm in (1, 3, 6, 12):
        BB = [boot(nm) for _ in range(2000)]; xs = np.array([sim(b, R, M, fa, nm)[0] for b in BB]) * 100
        print(f"   через {nm:2d} мес: медиана ${np.median(xs):,.0f} · плохой случай (1 из 10) ${np.quantile(xs, .1):,.0f} · хороший (1 из 10) ${np.quantile(xs, .9):,.0f} · в минусе {np.mean(xs < 100)*100:.0f}%")
