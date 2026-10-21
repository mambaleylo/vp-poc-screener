"""Two modules with their own risk: EMA (deployed list) at f, SMC at k x f; for each k the largest f with the 1-in-10
drawdown <= 45%; growth per year (median of the bootstrap). Plus regularity: trades per month, the share of weeks with
a trade, the share of trades in hours with 5+ entries, win rate."""
import sys
ARG = sys.argv[1:]
import json, numpy as np, collections
from mk import ts
q = ARG[0] if ARG else "0.99"
B = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))
S = json.load(open("smc_trades.json"))
def tl(lst, w): return [(x["t"], x["x"], x["r"], w) for x in lst if x["t"] >= ts(2022)]
rng = np.random.default_rng(7)
def boots(tr, nb=200):
    bl = {}
    for n_, x in enumerate(tr): bl.setdefault(x[0] // (30 * 86400), []).append(n_)
    bl = list(bl.values()); out = []
    for _ in range(nb):
        ev, base = [], 0
        for z, b in enumerate(rng.choice(len(bl), len(bl))):
            t0 = min(tr[n_][0] for n_ in bl[b])
            for n_ in bl[b]: ev += [(base + tr[n_][0] - t0, 0, n_, (z, n_)), (base + tr[n_][1] - t0, 1, n_, (z, n_))]
            base += 40 * 86400
        out.append(sorted(ev, key=lambda e: (e[0], -e[1])))
    return out
def grow(tr, B_, f):
    xs, ds = [], []
    for ev in B_:
        eq, peak, dd, risk = 1.0, 1.0, 0.0, {}
        for _, k, n_, u in ev:
            if k == 0: risk[u] = eq * f * tr[n_][3]
            else:
                eq += risk.pop(u) * tr[n_][2]; peak = max(peak, eq); dd = max(dd, 1 - eq / peak)
                if eq <= 0.02: eq, dd = 0.0, 1.0; break
        xs.append(eq); ds.append(dd)
    return float(np.median(xs)), float(np.quantile(ds, .9))
mo = (ts(2026, 10) - ts(2022)) / (30.4 * 86400)
def best(tr, tgt=0.45):
    tr = sorted(tr); B_ = boots(tr); b = None
    for f in np.arange(0.0025, 0.15, 0.0025):
        x, d = grow(tr, B_, f)
        if d <= tgt: b = (f, x)
        else: break
    return b
def regular(tr):
    t = np.array([x[0] for x in tr]); r = np.array([x[2] for x in tr])
    wk = collections.Counter(t // (7 * 86400)); nw = int((ts(2026, 10) - ts(2022)) / (7 * 86400))
    hr = collections.Counter(t // 3600); burst = sum(v for v in hr.values() if v >= 5) / len(t)
    return f"{len(t)/mo:4.1f}/мес, недель со сделкой {len(wk)/nw*100:3.0f}%, в пачках 5+/час {burst*100:3.0f}%, WR {np.mean(r>0)*100:3.0f}%, {r.mean():+.2f}R"
for nm, lst in (("EMA", B["emx"]), ("P/R", B["prv"]), (f"SMC q{q} бот", S[f"{q}_bot"]), (f"SMC q{q} проверка", S[f"{q}_chk"])):
    print(f"{nm:18s} {regular(tl(lst, 1))}", flush=True)
for base_nm, base in (("EMA", tl(B["emx"], 1)), ("EMA+P/R", tl(B["emx"], 1) + tl(B["prv"], 1))):
    for k in (0.0, 0.25, 0.5, 1.0):
        tr = base + (tl(S[f"{q}_bot"], k) if k > 0 else [])
        b = best(tr)
        print(f"{base_nm:8s} + SMC x{k:<4} риск {b[0]*100:5.2f}% (SMC {b[0]*k*100:4.2f}%)  x{b[1]**(12/mo):6.2f}/год   {regular(tr)}", flush=True)
