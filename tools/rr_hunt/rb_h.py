"""📈 Range breakout — a harness for hypotheses on the deployed rule (day: N 20, range < 2.5 ATR100; 12h: N 30, < 4.0;
the close beyond the range in the direction of the chart's own EMA200; stop 1.5 ATR; out at the close beyond the
20-bar low / high; at most 6 open per side per chart, the strongest breakout first). Events and the outcome grid from
rb_tf.py (rbtf24 / rbtf12); a check set = the same breakouts with the other range lengths (N) and K < 4."""
import os, glob, pickle, numpy as np, datetime as dt
from common import V, load, D
from mk import ts
import nx_feat
import rb_tf
STOPS, EXITS = rb_tf.STOPS, rb_tf.EXITS
NX = nx_feat.NAMES
CH = {24: (20, 2.5), 12: (30, 4.0)}
rows = []
for TFH in (24, 12):
    for k, fn in enumerate(sorted(glob.glob(f"{D}/rbtf{TFH}/*.pkl"))):
        sym = os.path.basename(fn)[:-4]
        for t, s, f, x, y in pickle.load(open(fn, "rb")):
            rows.append((t, s, TFH, sym, f["N"], f["rg"], bool(f["own200"]), f["brk"], x, y))
T = np.array([r[0] for r in rows], dtype=np.int64); SD = np.array([r[1] for r in rows]); TF = np.array([r[2] for r in rows])
SYM = np.array([r[3] for r in rows]); N = np.array([r[4] for r in rows]); RG = np.array([r[5] for r in rows], dtype=float)
OWN = np.array([r[6] for r in rows]); BRK = np.array([r[7] for r in rows], dtype=float)
X = np.stack([r[8] for r in rows]); Y = np.stack([r[9] for r in rows])
F = {n: X[:, i] for i, n in enumerate(NX)}
YR = np.minimum(np.array([dt.datetime.fromtimestamp(int(t), dt.timezone.utc).year for t in T]), 2025)
BOT = np.zeros(len(T), bool)
for tfh, (n0, k0) in CH.items():
    BOT |= (TF == tfh) & (N == n0) & (RG < k0) & OWN
CHECK = OWN & (RG < 4.0) & ~BOT          # the same idea, other range lengths / widths
START = ts(2021)
def lab(stop=1.5, ex="dc20"):
    r = Y[:, STOPS.index(stop), EXITS.index(ex), 0].astype(float); h = Y[:, STOPS.index(stop), EXITS.index(ex), 1]
    return r, np.nan_to_num(h, nan=1).astype(int)
def replay(mask, R, H, cap=6):
    out = []
    for tfh in (24, 12):
        idx = np.where(mask & (TF == tfh) & (T >= START) & ~np.isnan(R))[0]
        idx = idx[np.lexsort((-BRK[idx], T[idx]))]
        busy, act = {}, []
        for i in idx:
            t = T[i]; key = (SYM[i], SD[i])
            if busy.get(key, 0) > t: continue
            act = [a for a in act if a[0] > t]
            if sum(1 for a in act if a[1] == SD[i]) >= cap: continue
            end = t + H[i] * tfh * 3600; busy[key] = end; act.append((end, SD[i])); out.append(i)
    return np.array(sorted(out, key=lambda i: T[i]), dtype=np.int64)
rng = np.random.default_rng(1)
def END(tr, H): return T[tr] + H[tr] * TF[tr] * 3600
def port(tr, R, H, f, ev):
    eq, peak, dd, risk = 1.0, 1.0, 0.0, {}
    for _, k, i, u in ev:
        if k == 0: risk[u] = eq * f
        else:
            eq += risk.pop(u) * R[tr[i]]; peak = max(peak, eq); dd = max(dd, 1 - eq / peak)
            if eq <= 0.02: return 0.0, 1.0
    return eq, dd
def boots(tr, H, nb=250):
    mon = {}; E_ = END(tr, H)
    for i, j in enumerate(tr): mon.setdefault(int(T[j]) // (30 * 86400), []).append(i)
    bl = list(mon.values()); out = []
    for _ in range(nb):
        ev, base = [], 0
        for z, b in enumerate(rng.choice(len(bl), len(bl))):
            idx = bl[b]; t0 = min(T[tr[i]] for i in idx)
            ev += [(base + T[tr[i]] - t0, 0, i, (z, i)) for i in idx] + [(base + E_[i] - t0, 1, i, (z, i)) for i in idx]; base += 40 * 86400
        out.append(sorted(ev, key=lambda e: (e[0], -e[1])))
    return out
def line(nm, tr, R, H, target=0.45, grid=(0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.06, 0.08)):
    r = R[tr]; o = tr[np.argsort(END(tr, H), kind="stable")]
    run = w = 0
    for i in o: run = run + 1 if R[i] < 0 else 0; w = max(w, run)
    yrs = " ".join(f"{r[YR[tr] == y].mean():+.2f}" for y in (2021, 2022, 2023, 2024, 2025))
    wk = len(tr) / ((ts(2026, 10) - START) / 604800)
    bs = boots(tr, H); best = None
    for f in grid:
        rr = [port(tr, R, H, f, b) for b in bs]; ds = np.array([a[1] for a in rr])
        if np.quantile(ds, .9) <= target: best = (f, float(np.median([a[0] for a in rr])), float(np.median(ds)))
        else: break
    print(f"{nm:44s} {len(tr):5d} {wk:4.1f}/нед {r.mean():+.3f} WR {np.mean(r > 0)*100:3.0f}% подряд {w:2d} | {yrs} | "
          + (f"{best[0]*100:5.2f}%: x{best[1]:8.1f} (обычная {best[2]*100:.0f}%)" if best else "—"), flush=True)
