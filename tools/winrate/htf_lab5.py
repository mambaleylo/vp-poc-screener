"""📏 HTF lab round 5 — on the deployed rule's candidates (htf_export.py: long, OR q0.995, the bot coins, the reach filter,
the nearer-first touch order, cap 12, one per coin), the bot's 1h walk generalized:
  exits: take R, hold h, the close-stop TF, break-even (the stop to the entry after a 1h close at +X R), a trailing
  close-stop (after +a R: max close - b dATR, checked on the TF's closes), a partial take (f at p R);
  entry: a deeper limit (lv - d x dATR, waiting W hours after the touch; the stop stays at lv - 1 dATR, the hard at
  lv - 3 dATR; the take in R of the new risk); a fill bar that also reaches the stop -> the stop (worst case);
  filters: BTC regime (its daily close vs SMA 50 / 20-day return, days closed before the touch), the models' agreement.
Per config: n, R, WR, R-sum a year, by year; the lists for the money sim -> htf5_<name>.json."""
import sys, json, glob, math, numpy as np, warnings; warnings.filterwarnings("ignore")
sys.argv = ["x"]
from numba import njit
from lv_wf import load_dir, ts
import lv_engine as LE
from bt_trades import gate_sym
Dd = load_dir("lv2", LE.FNAMES); F = Dd["F"]; fam = F[:, 0].astype(int); T, SIDE, SYM, BOT = Dd["T"], Dd["SIDE"], Dd["SYM"], Dd["BOT"]
LV, J, DT = [], [], []
for fn in sorted(glob.glob("lv2/*.npz")):
    z = np.load(fn)
    if len(z["t"]) == 0: continue
    LV.append(z["lv"]); J.append(z["j"]); DT.append(z["datr"])
LV, J, DATR = np.concatenate(LV), np.concatenate(J).astype(np.int64), np.concatenate(DT)
zo = np.load("div_lv2_1537_sc.npz", allow_pickle=True); SCo, THRo = zo["SC"], zo["THR"].item()
zn = np.load("htf_long_sc.npz", allow_pickle=True); SCn, THRn = zn["SC"], zn["THR"].item()
HTF = fam <= 22
def pct(SCx, THRx):
    yr = np.array([int(np.datetime64(int(t), "s").astype("datetime64[Y]").astype(int) + 1970) for t in T]); p = np.full(len(T), np.nan)
    for Y, v in THRx.items():
        m = (yr == Y) & np.isfinite(SCx)
        if m.any(): p[m] = np.searchsorted(np.sort(v), SCx[m]) / len(v)
    return p
Po, Pn = pct(SCo, THRo), pct(SCn, THRn)
Q = float(ARGQ) if (ARGQ := (sys.argv[1] if len(sys.argv) > 1 else "")) else 0.995
base = HTF & (SIDE > 0) & (T >= ts(2023)) & BOT & np.isfinite(Po) & np.isfinite(Pn)
cand0 = np.where(base & ((Po >= 0.99) | (Pn >= 0.99)))[0]
BY = np.where((Po >= 0.995) & (Pn >= 0.995), 2, np.where((Po >= 0.995) | (Pn >= 0.995), 1, 0))
# BTC regime at the touch: the daily closes of the days closed before it
bT, bO, bH, bL, bC, bV = LE.load_np("BTCUSDT"); day = bT // 86400
dk = np.unique(day); dc = np.array([bC[day == d][-1] for d in dk])
sma50 = np.array([dc[max(0, i - 49):i + 1].mean() for i in range(len(dc))]); r20 = np.r_[np.full(20, np.nan), dc[20:] / dc[:-20] - 1]
di = np.searchsorted(dk, T // 86400) - 1
BTC_UP = np.where(di >= 0, dc[di.clip(0)] > sma50[di.clip(0)], False); BTC_R20 = np.where(di >= 0, r20[di.clip(0)], np.nan)

@njit
def walk(O, H, L, C, Tb, j, lv, datr, depth, win, hard_a, take, hold, kh, be_at, tr_at, tr_d, pf, pr, sfill=False):
    r0 = lv * datr / 100; fill = lv - depth * r0
    ssl = (fill - r0) if sfill else (lv - r0); hsl = (fill - hard_a * r0) if sfill else (lv - hard_a * r0)
    risk = fill - ssl
    n = len(C); b0 = -1
    if depth <= 0: b0 = j
    else:
        for b in range(j, min(n, j + win)):
            if L[b] <= fill: b0 = b; break
    if b0 < 0: return np.nan, 0, -1, 0.0, -1
    tp = fill + take * risk; e = min(n, b0 + hold); bank = 0.0; left = 1.0; be = False; mc = -1e18
    for q in range(e - b0):
        b = b0 + q
        cost = (0.001 + 0.0003 * (q + 1) / 24) * fill / risk
        stp = fill if be else hsl
        if L[b] <= stp or (q == 0 and depth > 0 and L[b] <= ssl):
            x = stp if L[b] <= stp else ssl
            if q > 0 and O[b] <= x: x = O[b]
            return bank + left * (x - fill) / risk - cost, b0 - j + q + 1, 2 if be else 0, x, b0 - j
        if pf > 0 and left == 1.0 and q > 0 and H[b] >= fill + pr * risk:
            bank += pf * pr; left = 1.0 - pf
        if q > 0 and H[b] >= tp:
            return bank + left * take - cost, b0 - j + q + 1, 1, tp, b0 - j
        if C[b] > mc: mc = C[b]
        if be_at > 0 and C[b] >= fill + be_at * risk: be = True
        if (Tb[b] + 3600) % (kh * 3600) == 0:
            lvl = ssl
            if tr_at > 0 and mc >= fill + tr_at * risk: lvl = max(ssl, mc - tr_d * r0)
            if C[b] <= lvl:
                return bank + left * (C[b] - fill) / risk - cost, b0 - j + q + 1, 4, C[b], b0 - j
    b = e - 1
    return bank + left * (C[b] - fill) / risk - (0.001 + 0.0003 * (e - b0) / 24) * fill / risk, b0 - j + e - b0, 3, C[b], b0 - j

BARS = {}
def bars(k):
    if k not in BARS: BARS[k] = LE.load_np(Dd["names"][k])
    return BARS[k]
OPEN = np.full(len(T), np.nan); PX = np.full(len(T), np.nan)
for k in sorted(set(SYM[cand0])):
    Tb, O, H, L, C, V = bars(k)
    for i in cand0[SYM[cand0] == k]: OPEN[i] = O[J[i]]; PX[i] = C[J[i] - 1]
cand0 = cand0[np.abs(PX[cand0] - LV[cand0]) / PX[cand0] * 100 <= 1.5 * DATR[cand0]]
NEAR = (OPEN - LV) / (LV * DATR / 100)

def run(name, q=0.995, depth=0.0, win=24, hard_a=3.0, take=3.0, hold=96, kh=4, be_at=0.0, tr_at=0.0, tr_d=1.0, pf=0.0, pr=1.5,
        filt=None, cap=12, save=False, prio=False, sfill=False):
    m = (Po[cand0] >= q) | (Pn[cand0] >= q)
    c = cand0[m]
    if filt is not None: c = c[filt(c)]
    R = {}; 
    for k in sorted(set(SYM[c])):
        Tb, O, H, L, C, V = bars(k)
        for i in c[SYM[c] == k]:
            R[i] = walk(O, H, L, C, Tb, int(J[i]), float(LV[i]), float(DATR[i]), depth, win, hard_a, take, hold, kh, be_at, tr_at, tr_d, pf, pr, sfill)
    o = c[np.lexsort((NEAR[c], -BY[c], T[c]))] if prio else c[np.lexsort((NEAR[c], T[c]))]
    busy, act, sel = {}, [], []
    for i in o:
        r, nb, kd, ex, off = R[i]
        if not np.isfinite(r): continue
        t = T[i] + off * 3600
        if busy.get(SYM[i], 0) > T[i]: continue
        act = [a for a in act if a > t]
        if len(act) >= cap: continue
        end = T[i] + nb * 3600; busy[SYM[i]] = end; act.append(end); sel.append(i)
    sel = np.array(sel, np.int64)
    rr = np.array([R[i][0] for i in sel]); tt = T[sel]
    yrs = " ".join(f"{Y % 100}:{rr[(tt >= ts(Y)) & (tt < ts(Y + 1))].mean():+.2f}({int(((tt >= ts(Y)) & (tt < ts(Y + 1))).sum())})" for Y in range(2023, 2027))
    span = (ts(2026, 10) - ts(2023)) / (365.25 * 86400)
    print(f"{name:44s} n {len(rr):4d} ({len(rr) / span:5.1f}/год) {rr.mean():+.3f}R WR {np.mean(rr > 0) * 100:3.0f}% ΣR/год {rr.sum() / span:+6.1f} | {yrs}", flush=True)
    if save:
        out = []
        for i in sel:
            r, nb, kd, ex, off = R[i]; gs, scl = gate_sym(Dd["names"][SYM[i]]); lv = float(LV[i]); r0 = lv * float(DATR[i]) / 100
            fill = lv - depth * r0; sb = fill if sfill else lv
            out.append({"s": gs, "t": int(T[i] + off * 3600), "x": int(T[i] + nb * 3600), "e": fill / scl, "sl": (sb - r0) / scl, "hs": (sb - hard_a * r0) / scl,
                        "r": round(float(r), 3), "by": int(BY[i])})
        json.dump(out, open(f"htf5_{name.split()[0]}.json", "w"))
    return rr
    return rr

print("== база и точка отсчёта", flush=True)
run("B0 как в боте", save=True)
print("== выходы", flush=True)
for tk in (2.5, 4, 5): run(f"X_t{tk} тейк {tk}R", take=tk)
for hd in (72, 120, 144, 192): run(f"X_h{hd} держим {hd}ч", hold=hd)
for tk, hd in ((4, 144), (5, 192), (6, 240)): run(f"X_t{tk}h{hd} тейк {tk}R {hd}ч", take=tk, hold=hd)
for kh in (1, 2, 8, 12, 24): run(f"X_k{kh} стоп по закрытию {kh}ч", kh=kh)
for ha in (2.0, 2.5, 4.0): run(f"X_ha{ha} аварийный {ha}", hard_a=ha)
for be in (1.0, 1.5, 2.0): run(f"X_be{be} безубыток после +{be}R", be_at=be)
for a, d in ((1.5, 1.0), (2.0, 1.0), (2.0, 1.5), (1.0, 1.5)): run(f"X_tr{a}_{d} трейл после +{a}R, {d} dATR", tr_at=a, tr_d=d)
for a, d, tk, hd in ((2.0, 1.0, 6, 192), (2.0, 1.5, 8, 240), (1.5, 1.5, 6, 192)): run(f"X_tr{a}_{d}_t{tk} трейл+тейк {tk}R {hd}ч", tr_at=a, tr_d=d, take=tk, hold=hd)
for f_, p_ in ((0.5, 1.5), (0.5, 2.0), (0.33, 1.0)): run(f"X_pf{f_}_{p_} частично {f_} на {p_}R", pf=f_, pr=p_)
for f_, p_, tk, hd in ((0.5, 1.5, 5, 192), (0.5, 2.0, 6, 192)): run(f"X_pf{f_}_{p_}_t{tk} частично+тейк {tk}R {hd}ч", pf=f_, pr=p_, take=tk, hold=hd)
print("== вход глубже уровня (лимитка)", flush=True)
for d in (0.15, 0.25, 0.4, 0.6):
    for w in (12, 48): run(f"E_d{d}_w{w} лимит −{d} dATR, ждём {w}ч", depth=d, win=w)
print("== фильтры", flush=True)
run("F_btc50 BTC выше SMA50", filt=lambda c: BTC_UP[c])
run("F_btcR20 BTC 20д > 0", filt=lambda c: BTC_R20[c] > 0)
run("F_btcR20n BTC 20д > −10%", filt=lambda c: BTC_R20[c] > -0.10)
run("F_both обе модели", filt=lambda c: BY[c] == 2)
run("F_one одна модель", filt=lambda c: BY[c] == 1)
print("== порог / лимит", flush=True)
for q in (0.993, 0.997): run(f"Q{q} порог q{q}", q=q)
for cp in (6, 20): run(f"C{cp} лимит {cp}", cap=cp)
