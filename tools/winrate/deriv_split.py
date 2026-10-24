"""⚡ pool trades split by the futures data at the entry (the last closed hour): funding, OI change 4h / 24h, the accounts'
long/short ratio z (30d), taker buy/sell z, top traders' position change z — each x the trade's side"""
import json, numpy as np, warnings; warnings.filterwarnings("ignore")
import ev2_engine as E2
from common import load
rr = [r for r in json.load(open("gh_dlm.json")) if r]
by = {}
for r in rr: by.setdefault(r["sym"], []).append(r)
def lr(x, k):
    o = np.full(len(x), np.nan); o[k:] = np.log(x[k:] / x[:-k]); return o
out = []
for sym, L in by.items():
    a = load(sym)
    if not a: continue
    T = np.array([c["time"] for c in a], np.int64); M = E2.metrics(sym, T)
    oi = M["oi"]; f = {"fund": M["fund"] * 1e4, "oi4": lr(oi, 4) * 100, "oi24": lr(oi, 24) * 100, "ls_z": E2.zs(M["ls_acc"], 24 * 30),
                       "tk_z": E2.zs(np.convolve(np.nan_to_num(M["taker"], nan=1.0), np.ones(24) / 24, mode="full")[:len(T)], 24 * 30),
                       "top_z": E2.zs(lr(M["top_pos"], 72), 24 * 30)}
    for r in L:
        k = np.searchsorted(T, r["te"] - 3600, side="right") - 1
        if k < 0: continue
        out.append(dict(R=r["R"], y=r["y"], **{n: float(v[k]) * r["d"] for n, v in f.items()}))
R = np.array([o["R"] for o in out]); Y = np.array([o["y"] for o in out])
print("сделок", len(out))
for n in ("fund", "oi4", "oi24", "ls_z", "tk_z", "top_z"):
    x = np.array([o[n] for o in out]); ok = np.isfinite(x)
    if ok.mean() < 0.5: print(n, "мало данных", ok.mean().round(2)); continue
    q = np.nanquantile(x, [0.2, 0.4, 0.6, 0.8]); g = np.digitize(x, q); g[~ok] = -1
    yd = [R[(g == 4) & (Y == y)].mean() - R[(g == 0) & (Y == y)].mean() for y in range(2022, 2027) if ((g == 4) & (Y == y)).sum() >= 15 and ((g == 0) & (Y == y)).sum() >= 15]
    print(f"{n:6s} есть {ok.mean()*100:.0f}% | " + " · ".join(f"q{k+1} {R[g == k].mean():+.2f}" for k in range(5)) + f" | верх-низ по годам: {' '.join(f'{v:+.2f}' for v in yd)}")
