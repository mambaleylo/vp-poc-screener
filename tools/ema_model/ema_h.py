"""EMA touches — a harness for exit / filter hypotheses on the deployed scheme (yearly walk-forward scores
er_sc_<LAB>.npz, fills >= 0.1% past the EMA, top q by score per year, one trade per coin & side, at most 12 per side).
Exits are re-simulated on 1h bars from the touch hour (the limit at the EMA)."""
import sys, numpy as np, pandas as pd, datetime as dt
from numba import njit
from common import load, D
from mk import ts
LAB = "F_0.75_4.0_3"
COLS = ["sym", "t", "j", "tf_s", "n_i", "lv", "side", "datr", "s_b24", "s_d_ema200", "s_d_ema50", "s_r24", "s_rsi_d", "s_rsi_tf", "beyond", "slope", "n_emas", "conf", LAB, LAB + "_h"]
d = pd.read_parquet(f"{D}/er_all.parquet", columns=COLS)
d["pen"] = pd.read_parquet(f"{D}/er_pen.parquet").pen.values
S = np.load(f"{D}/er_sc_{LAB}.npz")
T = d.t.values.astype(np.int64)
SC = np.full(len(d), np.nan); THR = {}
for Y in (2022, 2023, 2024, 2025):
    sc = S[str(Y)]
    te = (T >= ts(Y)) & (T < (ts(Y + 1) if Y < 2025 else ts(2027)))
    SC[te] = sc[te]
    ref = (T >= ts(Y - 1)) & (T < ts(Y) - 21 * 86400)
    THR[Y] = {q: float(np.quantile(sc[ref], q)) for q in (0.80, 0.90, 0.95, 0.97, 0.98, 0.99)}
YR = np.array([dt.datetime.fromtimestamp(int(t), dt.timezone.utc).year for t in T])
YR = np.minimum(YR, 2025)
def cand(q, mask=None):
    thr = np.array([THR[y][q] if y in THR else np.inf for y in YR])
    m = (YR >= 2022) & (d.pen.values >= 0.1) & (SC >= thr)
    if mask is not None: m &= mask
    return np.where(m)[0]
BARS = {}
def bars(sym):
    if sym not in BARS:
        cs = load(sym)
        BARS[sym] = tuple(np.array([c[k] for c in cs]) for k in ("open", "high", "low", "close"))
    return BARS[sym]
@njit(cache=True)
def sim1(O, H, L, C, j, side, fill, datr, a, take, hold, close_tf, hard, be):
    """a: the stop in daily ATR past the fill; take: R of that stop (0 = none); hold: hours;
    close_tf: 0 = the stop on touch, else the stop on the close of the close_tf-hour bar (aligned to UTC) with a
    hard stop at `hard` daily ATR; be: move the stop to the fill after +be R (0 = off). R per the sizing risk."""
    n = len(C)
    soft = fill * a * datr / 100
    hs_d = fill * (hard if close_tf > 0 else a) * datr / 100
    risk = hs_d
    stop = fill - side * hs_d
    sstop = fill - side * soft
    tp = fill + side * take * soft if take > 0 else 0.0
    moved = False
    e = min(n, j + hold)
    k = e - 1 - j; ex = C[e - 1]; kind = 3
    for q in range(e - j):
        b = j + q
        if (side > 0 and L[b] <= stop) or (side < 0 and H[b] >= stop):
            gap = (side > 0 and O[b] <= stop) or (side < 0 and O[b] >= stop)
            ex = O[b] if (gap and q > 0) else stop; k = q; kind = 0; break
        if take > 0 and q > 0 and ((side > 0 and H[b] >= tp) or (side < 0 and L[b] <= tp)):
            ex = tp; k = q; kind = 2; break
        if close_tf > 0 and ((b + 1) % close_tf == 0) and ((side > 0 and C[b] <= sstop) or (side < 0 and C[b] >= sstop)):
            ex = C[b]; k = q; kind = 1; break
        if be > 0 and not moved and ((side > 0 and H[b] >= fill + be * soft) or (side < 0 and L[b] <= fill - be * soft)):
            stop = fill + side * fill * 0.001; sstop = stop; moved = True
    r = (side * (ex - fill) - (0.001 + 0.0003 * (k + 1) / 24) * fill) / risk
    return r, k + 1, kind
def outcomes(idx, a=0.75, take=4.0, hold=72, close_tf=0, hard=0.0, be=0.0):
    R = np.full(len(d), np.nan); K = np.zeros(len(d), np.int64); KD = np.full(len(d), -1)
    sym, j, side, lv, datr = d.sym.values, d.j.values, d.side.values, d.lv.values, d.datr.values
    for i in idx:
        O, H, L, C = bars(sym[i])
        r, k, kd = sim1(O, H, L, C, int(j[i]), int(side[i]), float(lv[i]), float(datr[i]), a, take, hold, close_tf, hard, be)
        R[i], K[i], KD[i] = r, k, kd
    return R, K, KD
def replay(idx, R, K, cap=12):
    o = idx[np.lexsort((-SC[idx], T[idx]))]
    sym, side = d.sym.values, d.side.values
    busy, act, out = {}, [], []
    for i in o:
        t = T[i]; key = (sym[i], side[i])
        if busy.get(key, 0) > t or R[i] != R[i]: continue
        act = [a_ for a_ in act if a_[0] > t]
        if sum(1 for a_ in act if a_[1] == side[i]) >= cap: continue
        end = t + K[i] * 3600; busy[key] = end; act.append((end, side[i])); out.append(i)
    return np.array(out, dtype=np.int64)
rng = np.random.default_rng(1)
def port(tr, R, K, f, ev):
    eq, peak, dd, risk = 1.0, 1.0, 0.0, {}
    for _, k, i in ev:
        if k == 0: risk[i] = eq * f
        else:
            eq += risk.pop(i) * R[tr[i]]; peak = max(peak, eq); dd = max(dd, 1 - eq / peak)
            if eq <= 0.02: return 0.0, 1.0
    return eq, dd
def boots(tr, K, nb=250):
    mon = {}
    for i, j in enumerate(tr): mon.setdefault(int(T[j]) // (30 * 86400), []).append(i)
    bl = list(mon.values()); out = []
    for _ in range(nb):
        ev, base = [], 0
        for b in rng.choice(len(bl), len(bl)):
            idx = bl[b]; t0 = min(T[tr[i]] for i in idx)
            ev += [(base + T[tr[i]] - t0, 0, i) for i in idx] + [(base + T[tr[i]] + K[tr[i]] * 3600 - t0, 1, i) for i in idx]; base += 40 * 86400
        out.append(sorted(ev, key=lambda e: (e[0], -e[1])))
    return out
def eq_pain(tr, R, K, target, grid, nb=250):
    bs = boots(tr, K, nb); best = None
    for f in grid:
        rr = [port(tr, R, K, f, b) for b in bs]; ds = np.array([a[1] for a in rr])
        if np.quantile(ds, .9) <= target: best = (f, float(np.median([a[0] for a in rr])), float(np.median(ds)))
        else: break
    return best
def line(nm, tr, R, K, KD, target=0.45, grid=(0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10), pain=True):
    r = R[tr]; o = tr[np.argsort(T[tr] + K[tr] * 3600, kind="stable")]
    run = w = 0
    for i in o: run = run + 1 if R[i] < 0 else 0; w = max(w, run)
    yrs = " ".join(f"{r[YR[tr] == y].mean():+.2f}" for y in (2022, 2023, 2024, 2025))
    wk = len(tr) / ((ts(2026, 10) - ts(2022)) / 604800)
    s = f"{nm:44s} {len(tr):5d} {wk:4.1f}/нед {r.mean():+.3f} WR {np.mean(r > 0)*100:3.0f}% стопов {np.mean(np.isin(KD[tr], (0, 1)))*100:3.0f}% подряд {w:2d} | {yrs}"
    if pain:
        b = eq_pain(tr, R, K, target, grid)
        s += " | " + (f"{b[0]*100:5.2f}%: x{b[1]:8.1f} (обычная {b[2]*100:.0f}%)" if b else "—")
    print(s, flush=True)
