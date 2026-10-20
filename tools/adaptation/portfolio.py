"""P/R + EMA + 📈 together on the bot's backtest lists (vp_bt_trades.json), 2023-01 .. 2026-09 (the window all three
cover): the monthly correlation, the shared drawdowns, and the risk split at an equal 1-in-10 drawdown."""
import json, itertools, numpy as np, datetime as dt
bt = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))
T0, T1 = int(dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc).timestamp()), int(dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc).timestamp())
MODS = ("prv", "emx", "rbx")
NAME = {"prv": "P/R", "emx": "EMA", "rbx": "Пробой"}
tr = [(t["t"], t["x"], t["r"], m) for m in MODS for t in bt[m] if T0 <= t["t"] < T1 and t.get("r") is not None]
tr.sort()
print("сделок:", {NAME[m]: sum(1 for x in tr if x[3] == m) for m in MODS})
ym = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m")
months = sorted({ym(t) for t in range(T0, T1, 86400 * 27)})
mon = {m: np.array([sum(x[2] for x in tr if x[3] == m and ym(x[1]) == k) for k in months]) for m in MODS}
print("корреляция месячных R:")
for a, b in itertools.combinations(MODS, 2):
    print(f"  {NAME[a]} – {NAME[b]}: {np.corrcoef(mon[a], mon[b])[0, 1]:+.2f}")
both_bad = {f"{NAME[a]}+{NAME[b]}": int(np.sum((mon[a] < 0) & (mon[b] < 0))) for a, b in itertools.combinations(MODS, 2)}
print("месяцев, когда обе в минусе:", both_bad, "| все три:", int(np.sum((mon["prv"] < 0) & (mon["emx"] < 0) & (mon["rbx"] < 0))), "из", len(months))
idx = list(range(len(tr)))
def events(order_tr):
    return sorted([(a, 0, i) for i, (a, b, r, m) in enumerate(order_tr)] + [(b, 1, i) for i, (a, b, r, m) in enumerate(order_tr)], key=lambda e: (e[0], -e[1]))
rng = np.random.default_rng(11)
blocks = {}
for i, x in enumerate(tr): blocks.setdefault(ym(x[0]), []).append(i)
bl = list(blocks.values())
def boot():
    out, base, uid = [], 0, 0
    for z, b in enumerate(rng.choice(len(bl), len(bl))):
        t0 = min(tr[i][0] for i in bl[b])
        for i in bl[b]:
            out += [(base + tr[i][0] - t0, 0, i, (z, i)), (base + tr[i][1] - t0, 1, i, (z, i))]
        base += 32 * 86400
    return sorted(out, key=lambda e: (e[0], -e[1]))
B = [boot() for _ in range(300)]
def sim(ev, f):
    eq, peak, dd, risk = 1.0, 1.0, 0.0, {}
    for e in ev:
        k, i, u = e[1], e[2], e[3]
        if k == 0: risk[u] = eq * f[tr[i][3]]
        else:
            eq += risk.pop(u) * tr[i][2]; peak = max(peak, eq); dd = max(dd, 1 - eq / peak)
            if eq <= 0.02: return 0.0, 1.0
    return eq, dd
def stat(f):
    rr = [sim(b, f) for b in B]; xs = np.array([a[0] for a in rr]); ds = np.array([a[1] for a in rr])
    return float(np.median(xs)), float(np.median(ds)), float(np.quantile(ds, .9))
G = {"prv": (0, 0.02, 0.04, 0.06, 0.08), "emx": (0, 0.005, 0.01, 0.015), "rbx": (0, 0.0025, 0.005, 0.0075)}
res = []
for fp in G["prv"]:
    for fe in G["emx"]:
        for fr in G["rbx"]:
            if fp == fe == fr == 0: continue
            x, d50, d90 = stat({"prv": fp, "emx": fe, "rbx": fr}); res.append((fp, fe, fr, x, d50, d90))
print("\nриск P/R / EMA / Пробой -> рост за 45 мес (медиана), просадка обычная / 1 из 10")
for lim in (0.30, 0.45):
    ok = [r for r in res if r[5] <= lim]
    print(f"-- просадка 1 из 10 не больше {lim:.0%}: лучшие")
    for r in sorted(ok, key=lambda r: -r[3])[:6]:
        print(f"   {r[0]*100:3.0f}% / {r[1]*100:4.1f}% / {r[2]*100:4.2f}%: x{r[3]:9.1f} (~{(r[3] ** (1 / 45) - 1) * 100:+.1f}%/мес) | {r[4]*100:3.0f}% / {r[5]*100:3.0f}%")
    for m, nm in (("prv", "только P/R"), ("emx", "только EMA"), ("rbx", "только Пробой")):
        one = [r for r in ok if all(r[k] == 0 for k, mm in enumerate(MODS) if mm != m)]
        if one:
            r = max(one, key=lambda r: r[3])
            print(f"   {nm}: {r[0]*100:.0f}% / {r[1]*100:.1f}% / {r[2]*100:.2f}%: x{r[3]:.1f} | {r[4]*100:.0f}% / {r[5]*100:.0f}%")
