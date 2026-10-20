"""P/R from $30, one trade at a time (the bot's backtest list, chronological, the next signal after the previous closed),
the size so that a take = +X% of the deposit (all-in-like). Paths: the real order 2023–26 and a block bootstrap."""
import json, numpy as np
d = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))["prv"]
tr = sorted(d, key=lambda x: x["t"])
seq, free = [], 0
for x in tr:
    if x["t"] < free: continue
    seq.append(x); free = x["x"]
r = np.array([x["r"] for x in seq]); kinds = {}
for x in seq: kinds[x["k"]] = kinds.get(x["k"], 0) + 1
win_r = np.median(r[r > 0.5])
print(f"по одной сделке: {len(seq)} из {len(tr)} за {(seq[-1]['t'] - seq[0]['t']) / 86400 / 7:.0f} нед, WR {np.mean(r > 0)*100:.0f}%, в среднем {r.mean():+.3f}R, исходы {kinds}")
print(f"тейк = {win_r:.2f}R (по аварийному стопу); стоп по закрытию в среднем {r[(r < 0) & (r > -0.95)].mean():.2f}R; аварийный -1R: {np.sum(r <= -0.95)} раз")
wk = (seq[-1]['t'] - seq[0]['t']) / 86400 / 7; per_wk = len(seq) / wk
rng = np.random.default_rng(1)
def paths(f, n_tr, nb=20000, start=30.0, floor=5.0):
    out = np.empty(nb); hit = {10: 0, 100: 0, 1000: 0}; ruin = 0
    for b in range(nb):
        eq = start; i = rng.integers(0, len(r)); reached = set()
        for k in range(n_tr):
            x = r[(i + k) % len(r)] if (k % 10) else r[(i := rng.integers(0, len(r)))]   # blocks of 10 consecutive trades
            eq *= max(0.0, 1 + f * x)
            for m in hit:
                if eq >= start * m and m not in reached: reached.add(m); hit[m] += 1
            if eq < floor: ruin += 1; break
        out[b] = eq
    return out, {m: v / nb for m, v in hit.items()}, ruin / nb
for pct in (0.5, 0.7, 1.0):
    f = pct / win_r
    print(f"\n== тейк = +{pct*100:.0f}% депозита: риск до аварийного стопа {f*100:.0f}% депозита, стоп по закрытию ≈ {f*r[(r < 0) & (r > -0.95)].mean()*100:.0f}%, аварийный −{min(f, 1)*100:.0f}%")
    for months in (1, 3, 6, 12):
        n = int(round(per_wk * 4.35 * months))
        eqs, hit, ruin = paths(f, n)
        print(f"  {months:2d} мес (~{n} сделок): медиана ${np.median(eqs):,.0f} · ×10 {hit[10]*100:.0f}% · ×100 {hit[100]*100:.1f}% · ×1000 {hit[1000]*100:.2f}% · слив (<$5) {ruin*100:.0f}%")
eq = 30.0
for f in (0.7 / win_r,):
    e2 = 30.0; mn = 30.0
    for x in r: e2 *= max(0, 1 + f * x); mn = min(mn, e2)
    print(f"\nреальный порядок 2023–26, +70%: итог ${e2:,.0f}, минимум по пути ${mn:,.2f}")
for f in (0.04, 0.08, 0.15, 0.25):
    e2 = 30.0; pk = 30.0; dd = 0
    for x in r: e2 *= max(0, 1 + f * x); pk = max(pk, e2); dd = max(dd, 1 - e2 / pk)
    print(f"для сравнения риск {f*100:.0f}%: итог ${e2:,.0f}, макс. просадка {dd*100:.0f}%")
