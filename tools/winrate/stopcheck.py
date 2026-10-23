"""the user: "во всех стопах лимиток 4ч происходит вынос и потом всегда тейк". The deployed ⚡ trades (the mix, q0.99,
20 a side, 2022+): how many stopped trades reach the take later inside their 32 bars; exits where the stop counts
only on a 4h CLOSE beyond it (out at that close) with a hard intrabar stop further away; R in units of the HARD stop
(the position is sized by it), money at 20 positions x 4% (cautious / harsh)"""
import os; os.environ["TFH"] = "4"
import numpy as np, warnings; warnings.filterwarnings("ignore")
from numba import njit
exec(open("best_money.py").read().split("za = np.load")[0])
import s23_engine as E
za = np.load("s25_sc_4h_w1_0_A_base.npz", allow_pickle=True); zb = np.load("s25_sc_4h_w1_0_A_0-1-2-5-8.npz", allow_pickle=True)
ta, tb_ = za["THR"].item(), zb["THR"].item()
SC = (za["SC"] + zb["SC"]) / 2; THR = {Y: (ta[Y] + tb_[Y]) / 2 for Y in ta}
sel = select(D, 0, SC, THR, 0.99, 20, ~D["usdc"]); sel = sel[D["t"][sel] >= ts(2022)]
n127 = int((~D["new"]).sum())
cache = {}
def bars(sym):
    if sym not in cache: cache[sym] = E.load15(sym)
    return cache[sym]
@njit
def ex_close(O, H, L, C, f, s, fill, a, tk, cst, hst, hold, close_mode):
    """-> (pnl / fill, bars, took, the loss distance in ATR the position is sized by)"""
    n = len(C); e = min(n, f + hold); tp = fill + s * tk * a
    csl = fill - s * cst * a; hsl = fill - s * hst * a
    for q in range(e - f):
        b = f + q
        if (s > 0 and L[b] <= hsl) or (s < 0 and H[b] >= hsl):   # the hard stop, intrabar
            gap = (s > 0 and O[b] <= hsl) or (s < 0 and O[b] >= hsl)
            ex = O[b] if (gap and q > 0) else hsl
            return s * (ex - fill) - (0.0002 + 0.0005 + 0.0003 * (q + 1) / 6) * fill, q + 1, 0
        if q > 0 and ((s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp)):
            return s * (tp - fill) - (0.0002 + 0.0002 + 0.0003 * (q + 1) / 6) * fill, q + 1, 1
        if close_mode and ((s > 0 and C[b] <= csl) or (s < 0 and C[b] >= csl)):   # the close beyond the soft stop
            return s * (C[b] - fill) - (0.0002 + 0.0005 + 0.0003 * (q + 1) / 6) * fill, q + 1, 0
    return s * (C[e - 1] - fill) - (0.0002 + 0.0005 + 0.0003 * (e - f) / 6) * fill, e - f, 0
TR_ = []
for i in sel:
    dr = "s23_4hx" if i >= n127 else "s23_4h"
    sym = D["names"][D["sym"][i]]
    Tb, O, H, L, C, V = bars(sym); atr = E.wilder(H, L, C, 14)
    z = np.load(f"{dr}/{sym}.npz"); k = np.flatnonzero((z["t"] == D["t"][i]) & (z["side"] == D["side"][i]) & (z["fam"] == 2))[0]
    bi = int(z["i"][k]); s = int(D["side"][i]); a = float(atr[bi]); lv = (L[bi] if s > 0 else H[bi]) - s * a
    fb = next(b for b in range(bi + 1, bi + 5) if ((L[b] <= lv) if s > 0 else (H[b] >= lv)))
    fill = min(lv, O[fb]) if s > 0 else max(lv, O[fb])
    TR_.append((sym, fb, s, fill, a, int(Tb[fb]), bool(D["chk"][i] or D["new"][i])))
# (1) the stopped trades that reach the take later (inside the 32 bars from the fill)
st = later = 0
for sym, fb, s, fill, a, t, un in TR_:
    Tb, O, H, L, C, V = bars(sym); sl = fill - s * 2 * a; tp = fill + s * a
    e = min(len(C), fb + 32)
    for q in range(e - fb):
        b = fb + q
        if (L[b] <= sl) if s > 0 else (H[b] >= sl):
            st += 1
            if any(((H[x] >= tp) if s > 0 else (L[x] <= tp)) for x in range(b, e)): later += 1
            break
        if q > 0 and ((H[b] >= tp) if s > 0 else (L[b] <= tp)): break
print(f"сделок {len(TR_)}, стопов {st}, из них потом дошли до тейка за те же 32 свечи: {later} ({later / max(st, 1) * 100:.0f}%)")
roll = np.arange(ts(2024), ts(2025, 10) + 1, 7 * 86400.0)
VAR = [("стоп 2 ATR касанием (сейчас)", 2.0, 2.0, 0), ("по закрытию 2 ATR + аварийный 3", 2.0, 3.0, 1), ("по закрытию 2 + аварийный 4", 2.0, 4.0, 1),
       ("по закрытию 1.5 + аварийный 3", 1.5, 3.0, 1), ("по закрытию 2.5 + аварийный 3.5", 2.5, 3.5, 1), ("по закрытию 3 + аварийный 4", 3.0, 4.0, 1),
       ("касанием 3 ATR", 3.0, 3.0, 0), ("касанием 2.5 ATR", 2.5, 2.5, 0)]
for nm, cst, hst, cm in VAR:
    rows = []
    for sym, fb, s, fill, a, t, un in TR_:
        Tb, O, H, L, C, V = bars(sym)
        pnl, k, w = ex_close(O, H, L, C, fb, s, fill, a, 1.0, cst, hst, 32, cm)
        rows.append((t, t + k * 14400, pnl / (hst * a), hst * a / fill, un, w))
    rows.sort(); t0 = np.array([r[0] for r in rows], float); t1 = np.array([r[1] for r in rows], float)
    R = np.array([r[2] for r in rows]); STv = np.clip(np.array([r[3] for r in rows]), 0.002, 0.5); W = np.array([r[5] for r in rows]); U = np.array([r[4] for r in rows])
    h = t0 >= ts(2025, 10); res = {}
    for sh, lab in ((-0.025, "c"), (-0.04, "h")):
        y = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, sh) for s_ in roll])
        res[lab] = (np.median(y[:, 0]), np.percentile(y[:, 0], 10), np.median(y[:, 1]), np.percentile(y[:, 1], 90))
    c, hh = res["c"], res["h"]
    print(f"{nm:34s} WR {W.mean()*100:.0f}% (невид {W[U].mean()*100:.0f}%, посл.12м {W[h].mean()*100:.0f}%) {R.mean():+.3f}R на аварийный стоп | 4%: медиана ${c[0]:,.0f} 10% ${c[1]:,.0f} просадка {c[2]*100:.0f}%/{c[3]*100:.0f}% | жёстко ${hh[0]:,.0f}", flush=True)
