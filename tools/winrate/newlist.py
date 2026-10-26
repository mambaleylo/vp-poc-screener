"""new-listing short: the coins whose Binance futures 1h history starts after 2021-06 (the listing); short at the close
of day D, the stop k x the mean daily range of the first D days above (touch), hold H days; R = the move / the stop
distance after costs (0.1% a side + 8h funding at 0.01% the short receives — ignored, conservative). Grid; by year;
bot / check coins; the list for the money sim -> newlist_<D>_<H>_<k>.json"""
import json, numpy as np, calendar
from lv_engine import load_np
from bt_trades import gate_sym
ts = lambda y, m=1, d=1: calendar.timegm((y, m, d, 0, 0, 0))
sp = json.load(open("lv/split.json")); BOT = set(sp["bot"])
newc = [s for s in sp["bot"] + sp["chk"] if load_np(s)[0][0] >= ts(2021, 6)]
DATA = {s: load_np(s) for s in newc}
def run(D_, Hd, k, save=False):
    out = []
    for s in newc:
        Ts, Os, Hs, Ls, Cs, Vs = DATA[s]; j0 = D_ * 24
        if len(Cs) < j0 + 24: continue
        e = Cs[j0 - 1]; rng = (Hs[:j0].max() - Ls[:j0].min()) / D_; sl = e + k * rng; st = (sl - e) / e
        x = None; j1 = min(len(Cs), j0 + Hd * 24)
        for j in range(j0, j1):
            if Hs[j] >= sl: x = max(sl, Os[j]); break
        if x is None: x = Cs[j1 - 1]
        R = ((e - x) / e - 0.002) / st
        out.append({"s": s, "t": int(Ts[j0]), "x": int(Ts[min(j, j1 - 1)] + 3600), "e": float(e), "sl": float(sl), "r": float(R), "st": float(st), "bot": s in BOT})
    if save:
        js = []
        for o in out:
            gs, scl = gate_sym(o["s"]); js.append({"s": gs, "d": -1, "t": o["t"], "x": o["x"], "e": o["e"] / scl, "sl": o["sl"] / scl, "hs": o["sl"] / scl, "r": o["r"]})
        json.dump(js, open(f"newlist_{D_}_{Hd}_{k}.json", "w"))
    return out
def line(nm, out):
    r = np.array([o["r"] for o in out]); t = np.array([o["t"] for o in out]); b = np.array([o["bot"] for o in out])
    yr = " ".join(f"{Y % 100}:{r[(t >= ts(Y)) & (t < ts(Y + 1))].mean():+.2f}({((t >= ts(Y)) & (t < ts(Y + 1))).sum()})" for Y in range(2021, 2027) if ((t >= ts(Y)) & (t < ts(Y + 1))).any())
    print(f"  {nm:26s} n {len(r):3d} {r.mean():+.3f}R WR {np.mean(r > 0)*100:3.0f}% | бота {r[b].mean():+.2f}({b.sum()}) контр. {r[~b].mean():+.2f}({(~b).sum()}) | стоп мед {np.median([o['st'] for o in out])*100:.0f}% | {yr}", flush=True)
print("монет:", len(newc))
for D_ in (1, 3, 5, 7, 10):
    for Hd in (7, 14, 21):
        for k in (1.0, 1.5, 2.0, 3.0):
            line(f"день {D_:2d}, {Hd:2d} д, стоп {k}", run(D_, Hd, k, save=(D_, Hd, k) in ((7, 14, 2.0), (3, 14, 2.0), (5, 14, 2.0), (7, 21, 2.0))))
