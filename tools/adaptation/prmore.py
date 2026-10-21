"""P/R, more trades (the user: "как в p/r увеличить количество сделок"): the deployed rule (the limit 0.3 ATR / 3 h, stops
3 / 6 ATR, take 4.5 ATR, 48 h, BTC filters 4% / 1%, cap 12 per side) with lower score thresholds (q 0.97 .. 0.995 of
the last 12 months, quarterly models of pr_sel2.py), the 4h events too, a bigger cap, and 84 more Binance coins
(volume >= 150M $ a month, history from 2025-06 or earlier; scored by the same quarterly models, never trained on them).
2023-01 .. 2026-09; growth at an equal 1-in-10 drawdown (45%)."""
import glob, os, pickle, numpy as np
import prv_wf as W
from wr_eval import stats
from mk import ts
QS = (0.95, 0.97, 0.975, 0.98, 0.985, 0.99, 0.995)
def side_tf(X): return X[:, W.NAMES.index("side")].astype(int), X[:, W.NAMES.index("tf")].astype(int)
# ---- the 127 coins
S = np.load(f"{W.D}/prv_sel2.npz"); z = np.load(f"{W.D}/p2_base.npz")
OLD_SY = np.array([os.path.basename(f)[:-4] for f in sorted(glob.glob(f"{W.D}/prv_ev/*.npz"))])[W.SY]
def pack(T, SY, SD, TF, X, R, K, idx, sc, thr):
    m = np.zeros(len(T), bool); m[idx] = True
    SC = np.full(len(T), np.nan); SC[idx] = sc
    TH = {q: np.full(len(T), np.inf) for q in QS}
    for q in QS: TH[q][idx] = thr[q]
    btc = (SD * X[:, W.NAMES.index("b_r24")] > -4) & (SD * X[:, W.NAMES.index("b_r1")] > -1)
    R = np.where(np.abs(R) > 20, np.nan, R)
    return dict(T=T, SY=SY, SD=SD, TF=TF, R=R, END=T + (K + 1) * TF * 3600, SC=SC, TH=TH, BTC=btc)
OLD = pack(W.T, OLD_SY, W.SD, W.TF, W.X, z["cs"].astype(float), z["k"].astype(int), S["idx"], S["sc"],
           {q: S[f"t{int(round(q * 1000))}"] for q in QS})
# ---- the extra coins, scored by the quarterly models
NEW = None
fs = sorted(glob.glob(f"{W.D}/prv_ev_new/*.npz"))
if fs and os.path.exists(f"{W.D}/p2_new.npz"):
    Xs, Ts, Ss = [], [], []
    for f in fs:
        e = np.load(f)
        if len(e["t"]): Xs.append(e["X"]); Ts.append(e["t"]); Ss.append(np.full(len(e["t"]), os.path.basename(f)[:-4]))
    X = np.concatenate(Xs); T = np.concatenate(Ts); SY = np.concatenate(Ss); SD, TF = side_tf(X)
    models = pickle.load(open(f"{W.D}/prv_models_q.pkl", "rb"))
    idx, sc, thr = [], [], {q: [] for q in QS}
    for t0, t1, s, bst, th in models:
        ti = np.where((T >= t0) & (T < t1) & (SD == s))[0]
        if not len(ti): continue
        idx.append(ti); sc.append(sum(b.predict(X[ti]) for b in bst) / len(bst))
        for q in QS: thr[q].append(np.full(len(ti), th[q]))
    zn = np.load(f"{W.D}/p2_new.npz")
    NEW = pack(T, SY, SD, TF, X, zn["cs"].astype(float), zn["k"].astype(int), np.concatenate(idx), np.concatenate(sc), {q: np.concatenate(thr[q]) for q in QS})
    print("extra coins", len(fs), "events", len(T), flush=True)
def trades(sets, q, tfs=(1,), cap=12):
    ev = []
    for di, D_ in enumerate(sets):
        m = (D_["SC"] >= D_["TH"][q]) & np.isin(D_["TF"], tfs) & D_["BTC"] & ~np.isnan(D_["R"]) & (D_["T"] >= ts(2023))
        for j in np.where(m)[0]: ev.append((int(D_["T"][j]), -float(D_["SC"][j]), str(D_["SY"][j]), int(D_["SD"][j]), float(D_["R"][j]), int(D_["END"][j]), (di, int(j))))
    ev.sort(); busy, act, out = {}, [], []
    for t, _, sy, s, r, end, ref in ev:
        if busy.get((sy, s), 0) > t: continue
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == s) >= cap: continue
        busy[(sy, s)] = end; act.append((end, s)); out.append((t, end, r, s, ref))
    return out
def yrs(tr):
    r = np.array([x[2] for x in tr]); t = np.array([x[0] for x in tr])
    return " ".join(f"{r[(t >= ts(y)) & (t < ts(y + 1))].mean():+.2f}" for y in (2023, 2024, 2025, 2026))
if __name__ == "__main__":
    G = tuple(np.round(np.arange(0.005, 0.20, 0.005), 4))
    def line(nm, tr): print("   годы", yrs(tr)); stats(nm, tr, ts(2023), 0.45, grid=G)
    print("\n=== 127 монет: порог", flush=True)
    for q in (0.995, 0.99, 0.985, 0.98, 0.975, 0.97): line(f"q{q}{' (сейчас)' if q == 0.99 else ''}", trades([OLD], q))
    print("\n=== 127 монет: + 4ч события, лимит", flush=True)
    for q in (0.99, 0.98): line(f"q{q} 1ч+4ч", trades([OLD], q, tfs=(1, 4)))
    for q in (0.99, 0.98): line(f"q{q} лимит 20", trades([OLD], q, cap=20))
    if NEW is not None:
        print("\n=== новые монеты отдельно", flush=True)
        for q in (0.99, 0.98): line(f"новые {len(fs)}, q{q}", trades([NEW], q))
        print("\n=== 127 + новые вместе", flush=True)
        for q in (0.99, 0.985, 0.98): line(f"все, q{q}", trades([OLD, NEW], q))
        for q in (0.99, 0.98): line(f"все, q{q}, лимит 20", trades([OLD, NEW], q, cap=20))
