"""EMA round 4: the deployed v0.99.664 rule's label for every LONG touch — the limit 0.2 daily ATR past the EMA filled in
the touch hour (the low >= 0.1% past it), stop 0.75 daily ATR, 1/3 off at +1R -> break-even, take 4R, 72 h; 0 when
it does not fill (the order's expected value). -> er_lab_deep.npz (y, h)"""
import numpy as np, pandas as pd
from numba import njit
from common import load, D
d = pd.read_parquet(f"{D}/er_all.parquet", columns=["sym", "j", "lv", "side", "datr"])
d["pen"] = pd.read_parquet(f"{D}/er_pen.parquet").pen.values
@njit(cache=True)
def lab(O, H, L, C, js, lvs, drs, pens, out, hh):
    for z in range(len(js)):
        j = js[z]; dp = 0.2 * drs[z]
        if pens[z] < 0.1 + dp: out[z] = 0.0; hh[z] = 1; continue
        fill = lvs[z] * (1 - dp / 100); risk = fill * 0.75 * drs[z] / 100
        stop = fill - risk; tp = fill + 4 * risk; took = False
        e = min(len(C), j + 72); k = e - 1 - j; ex = C[e - 1]
        for q in range(e - j):
            b = j + q
            if L[b] <= stop:
                ex = O[b] if (O[b] <= stop and q > 0) else stop; k = q; break
            if q > 0:
                fav = (H[b] - fill) / risk
                if not took and fav >= 1.0: took = True; stop = fill
                if fav >= 4.0: ex = tp; k = q; break
        fee = (0.001 + 0.0003 * (k + 1) / 24) * fill / risk
        rest = (ex - fill) / risk
        out[z] = (0.33 + 0.67 * rest if took else rest) - fee; hh[z] = k + 1
y = np.full(len(d), np.nan); h = np.ones(len(d), np.int64)
for sym, g in d[d.side.values > 0].groupby("sym"):
    cs = load(sym); O, H, L, C = (np.array([c[k] for c in cs]) for k in ("open", "high", "low", "close"))
    o = np.empty(len(g)); hh = np.empty(len(g), np.int64)
    lab(O, H, L, C, g.j.values.astype(np.int64), g.lv.values.astype(float), g.datr.values.astype(float), g.pen.values.astype(float), o, hh)
    y[g.index.values] = o; h[g.index.values] = hh
np.savez(f"{D}/er_lab_deep.npz", y=y, h=h)
m = ~np.isnan(y); print("longs", m.sum(), "filled", (y[m] != 0).sum(), "mean filled", np.mean(y[m][y[m] != 0]))
