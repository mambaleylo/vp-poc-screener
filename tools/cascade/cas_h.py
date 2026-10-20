"""EMA cascade harness on the saved walk-forward scores (cas_sel.py): q 0.995 = a bot-like set, q 0.98 = the check set;
one trade per coin & side until it exits (re-simulated on 1h), at most 12 per side; equal pain vs P/R"""
import sys, glob, os, json, datetime as dt
ARGS = sys.argv[1:]
import numpy as np
from common import load, D
from mk import ts
from cas_ev import label, ema, NS
from nx_h import pain
z = np.load(f"{D}/cas_all.npz"); X, T, SY = z["X"], z["T"], z["SY"]; SD = X[:, 0].astype(int)
S = np.load(f"{D}/" + os.environ.get("CAS_SEL", "cas_sel.npz"))
SYMS = [os.path.basename(f)[:-4] for f in sorted(glob.glob(f"{D}/cas/*.npz"))]
YR = np.array([dt.datetime.fromtimestamp(int(t), dt.timezone.utc).year for t in T])
STOPS = {"1": 1.0, "1.5": 1.5, "2": 2.0, "sw": -1.0}
B = {}
def bars(k):
    if k not in B:
        cs = load(SYMS[k]); O = np.array([c["open"] for c in cs]); H = np.array([c["high"] for c in cs]); L = np.array([c["low"] for c in cs]); C = np.array([c["close"] for c in cs])
        tm = np.array([c["time"] + 3600 for c in cs]); E = np.stack([ema(C, n) for n in NS])
        tr = np.maximum(H[1:] - L[1:], np.maximum(abs(H[1:] - C[:-1]), abs(L[1:] - C[:-1]))); tr = np.r_[H[0] - L[0], tr]
        atr = np.full(len(C), np.nan); a = tr[:14].mean()
        for i in range(14, len(C)): a = (a * 13 + tr[i]) / 14; atr[i] = a
        B[k] = (O, H, L, C, E.max(0), E.min(0), atr, tm)
    return B[k]
def trades(nm, q, side=(1, -1), mask=None, take=None, stop=None, hold=None):
    a, b, c = nm.split("_"); sk = STOPS[stop or a]; ex = float((take or b)[1:]) if (take or b)[0] == "t" else 0.0; h = int(hold or c)
    ev = []
    for s in side:
        sc = S[f"sc_{nm}_{s}"]
        if f"thrv_{nm}_{s}_{q}" in S.files: tv = S[f"thrv_{nm}_{s}_{q}"]     # cas_sel3: a threshold per event (its fold)
        else:
            thr = np.array([S[f"thr_{nm}_{s}_{q}_{y}"] if f"thr_{nm}_{s}_{q}_{y}" in S.files else np.inf for y in range(2000, 2030)])
            tv = thr[np.clip(YR - 2000, 0, 29)]
        m = (SD == s) & ~np.isnan(sc) & (sc >= tv)
        if mask is not None: m &= mask
        for r in np.where(m)[0]: ev.append((int(T[r]), -float(sc[r]), int(SY[r]), s, int(r)))
    ev.sort(); busy, act, out = {}, [], []
    for t, _, sy, s, r in ev:
        if busy.get((sy, s), 0) > t: continue
        act = [x for x in act if x[0] > t]
        if sum(1 for x in act if x[1] == s) >= 12: continue
        O, H, L, C, TOP, BOT, atr, tm = bars(sy); i = int(np.searchsorted(tm, t))
        if i >= len(tm) or tm[i] != t: continue
        R, k = label(O, H, L, C, TOP, BOT, i, s, atr[i], sk, ex, h)
        if R != R: continue
        end = t + 3600 * (k + 1); busy[(sy, s)] = end; act.append((end, s)); out.append((t, end, float(R), s, r))
    return out
def line(nm, tr, q, f0=2022):
    tr = [x for x in tr if x[0] >= ts(f0)]
    if not tr: print(nm, "—"); return
    r = np.array([x[2] for x in tr]); t = np.array([x[0] for x in tr]); o = sorted(tr, key=lambda x: x[1]); run = w = 0
    for x in o: run = run + 1 if x[2] < 0 else 0; w = max(w, run)
    yrs = " ".join(f"{r[(t >= ts(y)) & (t < ts(y + 1))].mean():+.2f}" for y in range(f0, 2027))
    wk = (ts(2026, 10) - ts(f0)) / (7 * 86400)
    target = 0.45 if q >= 0.995 else 0.50
    grid = (0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.06, 0.08) if q >= 0.99 else (0.001, 0.002, 0.003, 0.005, 0.0075, 0.01, 0.015, 0.02)
    b = pain(tr, target, grid)
    print(f"{nm:44s} {len(r):5d} {len(r)/wk:4.1f}/нед {r.mean():+.3f} WR {np.mean(r > 0)*100:3.0f}% подряд {w:2d} | {yrs} | " + (f"{b[0]*100:.2f}%: x{b[1]:.1f} (обычная {b[2]*100:.0f}%)" if b else "—"), flush=True)
def prv():
    d = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))["prv"]
    return [(x["t"], x["x"], x["r"], x["d"], 0) for x in d]
def monthly(tr):
    m = {}
    for x in tr: m[x[1] // (30 * 86400)] = m.get(x[1] // (30 * 86400), 0) + x[2]
    return m
if __name__ == "__main__":
    P = prv(); print("P/R бот:"); line("P/R (бэктест бота, 1ч, стоп по закрытию)", P, 0.995, 2023)
    for nm in [n[3:-2] for n in S.files if n.startswith("sc_") and n.endswith("_1")]:
        print(f"\n== {nm}")
        for q in (0.995, 0.99, 0.98):
            tr = trades(nm, q); line(f"q{q} обе стороны", tr, q); line(f"q{q} обе стороны с 2023", tr, q, 2023)
            if q == 0.995:
                line("q0.995 только шорт", [x for x in tr if x[3] < 0], q); line("q0.995 только лонг", [x for x in tr if x[3] > 0], q)
                a, b = monthly(tr), monthly(P); ks = sorted(set(a) & set(b))
                print(f"  корреляция по месяцам с P/R: {np.corrcoef([a[k] for k in ks], [b[k] for k in ks])[0, 1]:+.2f} ({len(ks)} мес)")
                pr_t = {(x[0] // 3600) for x in P}
                print(f"  совпадение входов по часу с P/R: {sum(1 for x in tr if x[0] // 3600 in pr_t)}")
