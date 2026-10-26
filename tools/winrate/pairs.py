"""Pairs trading (Engle-Granger stat-arb, the GitHub / textbook form) on the 1h closes: every Monday 00:00 UTC, among
the 50 coins of the set with the largest quote volume over the 30 days before (full history there): OLS ln A = a + b ln B
on those 30 days, the residual's Dickey-Fuller t (de_t = g e_t-1), its half-life; pairs with t < T_MAX, half-life
HL_MIN..HL_MAX h, 0.2 < b < 5; the best K by t, each coin in one pair. The next 7 days (fixed a, b, the residual's mean
/ std of the formation): z at each hour's close; |z| >= Z_IN -> in at the next hour's open (short the rich leg, long the
cheap one, notional B = b x A); out at the next open after z crosses 0, |z| >= Z_STOP, or HOLD h. R = the spread move
/ the stop distance ((Z_STOP - Z_IN) sigma), minus fees 0.1% a side per leg and the real 8h funding of both legs.
argv: bot | chk  [variant]"""
import sys, json, os, numpy as np, calendar
ARGV = sys.argv[1:]
from numba import njit
from lv_engine import load_np
SET = ARGV[0] if len(ARGV) > 0 else "bot"; VAR = ARGV[1] if len(ARGV) > 1 else "base"
P = dict(base=dict(T_MAX=-3.9, HL=(4, 48), K=10, Z_IN=2.0, Z_STOP=4.0, HOLD=120, F=30),
         z25=dict(T_MAX=-3.9, HL=(4, 48), K=10, Z_IN=2.5, Z_STOP=4.5, HOLD=120, F=30),
         f60=dict(T_MAX=-3.9, HL=(4, 72), K=10, Z_IN=2.0, Z_STOP=4.0, HOLD=120, F=60),
         strict=dict(T_MAX=-4.5, HL=(4, 24), K=6, Z_IN=2.0, Z_STOP=4.0, HOLD=72, F=30),
         loose=dict(T_MAX=-3.4, HL=(2, 72), K=15, Z_IN=2.0, Z_STOP=4.0, HOLD=120, F=30))[VAR]
ts = lambda y, m=1, d=1: calendar.timegm((y, m, d, 0, 0, 0))
sp = json.load(open("lv/split.json")); syms = sp["bot"] if SET == "bot" else sp["chk"]
H0, H1 = ts(2021, 6), ts(2026, 10); NH = (H1 - H0) // 3600
LO = np.full((len(syms), NH), np.nan); LC = np.full((len(syms), NH), np.nan); QV = np.zeros((len(syms), NH)); FU = np.zeros((len(syms), NH))
for k, s in enumerate(syms):
    T, O, H, L, C, V = load_np(s); i = (T - H0) // 3600; m = (i >= 0) & (i < NH)
    LO[k, i[m]] = np.log(O[m]); LC[k, i[m]] = np.log(C[m]); QV[k, i[m]] = V[m] * C[m]
    fn = f"data/funding/{s}.csv"
    if os.path.exists(fn):
        f = np.loadtxt(fn, delimiter=",", ndmin=2)
        if len(f):
            fi = ((f[:, 0].astype(np.int64) - H0) // 3600); mm = (fi >= 0) & (fi < NH); FU[k, fi[mm]] = f[mm, 1]
CF = np.cumsum(FU, 1)
@njit
def stats(y, x):
    n = len(y); mx = x.mean(); my = y.mean(); b = ((x - mx) * (y - my)).sum() / max(((x - mx) ** 2).sum(), 1e-18); a = my - b * mx
    e = y - a - b * x; e0 = e[:-1]; de = e[1:] - e[:-1]
    g = (e0 * de).sum() / max((e0 * e0).sum(), 1e-18); res = de - g * e0
    se = np.sqrt((res * res).sum() / (n - 2) / max((e0 * e0).sum(), 1e-18))
    return a, b, g / se, (-np.log(2) / g if g < 0 else 1e9), e.mean(), e.std()
@njit
def trade(LOa, LCa, LOb, LCb, h0, h1, a, b, mu, sd, zin, zst, hold, out, no):
    pos = 0; hi = 0; se = 0.0; zi = 0.0; zp = 0.0; dead = False
    h = h0
    while h < h1 + hold and h < len(LCa) - 1:
        if not (np.isfinite(LCa[h]) and np.isfinite(LCb[h]) and np.isfinite(LOa[h + 1]) and np.isfinite(LOb[h + 1])):
            h += 1; continue
        z = (LCa[h] - a - b * LCb[h] - mu) / sd
        if pos == 0:
            if h < h1 and not dead and h > h0 and abs(zp) < zin and zin <= abs(z) < zst and no < 399:
                pos = -1 if z > 0 else 1; hi = h + 1; se = LOa[h + 1] - b * LOb[h + 1]; zi = z
        else:
            if pos * z >= 0 or abs(z) >= zst or h + 1 - hi >= hold:
                sx = LOa[h + 1] - b * LOb[h + 1]
                out[no, 0] = hi; out[no, 1] = h + 1; out[no, 2] = pos * (sx - se); out[no, 3] = pos; out[no, 4] = zi
                out[no, 5] = 1.0 if abs(z) >= zst else (2.0 if h + 1 - hi >= hold else 0.0); no += 1; pos = 0
                if abs(z) >= zst: dead = True
        zp = z
        h += 1
    return no
tr = []
mon = np.arange(ts(2022, 1, 3), H1 - 7 * 86400, 7 * 86400)
for w in mon:
    hw = (w - H0) // 3600; hf = hw - P["F"] * 24
    ok = np.isfinite(LC[:, hf:hw]).all(1)
    q = np.where(ok, QV[:, hf:hw].sum(1), -1); uni = np.argsort(-q)[:50]; uni = uni[q[uni] > 0]
    cands = []
    for ii in range(len(uni)):
        for jj in range(ii + 1, len(uni)):
            i, j = uni[ii], uni[jj]
            for A_, B_ in ((i, j), (j, i)):
                a, b, t, hl, mu, sd = stats(LC[A_, hf:hw], LC[B_, hf:hw])
                if t < P["T_MAX"] and P["HL"][0] <= hl <= P["HL"][1] and 0.2 < b < 5: cands.append((t, A_, B_, a, b, mu, sd))
                break   # one direction per pair (A = the more liquid)
    cands.sort(); used = set(); pick = []
    for c in cands:
        if c[1] in used or c[2] in used: continue
        used |= {c[1], c[2]}; pick.append(c)
        if len(pick) >= P["K"]: break
    for t, A_, B_, a, b, mu, sd in pick:
        out = np.zeros((400, 6)); no = trade(LO[A_], LC[A_], LO[B_], LC[B_], hw, hw + 168, a, b, mu, sd, P["Z_IN"], P["Z_STOP"], P["HOLD"], out, 0)
        for k in range(no):
            hi, hx, ds, pos, zi, kind = out[k]; hi, hx = int(hi), int(hx)
            risk = (P["Z_STOP"] - P["Z_IN"]) * sd
            fee = 0.002 * (1 + b)
            fund = pos * (CF[A_, hx - 1] - CF[A_, hi - 1]) - pos * b * (CF[B_, hx - 1] - CF[B_, hi - 1])   # long pays the rate
            R = (ds - fee - fund) / risk
            tr.append({"a": syms[A_], "b": syms[B_], "beta": round(float(b), 3), "t": int(H0 + hi * 3600), "x": int(H0 + hx * 3600), "r": round(float(R), 3),
                       "st": float(risk / (1 + b)), "k": int(kind), "sd": float(sd)})
json.dump(tr, open(f"pairs_{SET}_{VAR}.json", "w"))
r = np.array([x["r"] for x in tr]); t = np.array([x["t"] for x in tr]); k = np.array([x["k"] for x in tr])
yr = lambda Y: (t >= ts(Y)) & (t < ts(Y + 1))
print(f"{SET} {VAR}: сделок {len(r)} ({len(r) / 4.75:.0f}/год) ср.R {r.mean():+.3f} WR {np.mean(r > 0)*100:.0f}% стопов {np.mean(k == 1)*100:.0f}% по времени {np.mean(k == 2)*100:.0f}% | "
      + " ".join(f"{Y % 100}:{r[yr(Y)].mean():+.2f}({yr(Y).sum()},Σ{r[yr(Y)].sum():+.0f})" for Y in range(2022, 2027)) + f" | стоп медиана {np.median([x['st'] for x in tr])*100:.2f}%", flush=True)
