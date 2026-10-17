"""trend families (4h / 1d) with gates from the coin's own trend, the weekly trend, strength vs BTC and the market:
one trade per coin & side until exit, at most CAP per side; picked on 2021–23, judged on 2024 / 2025–26"""
import glob, os, itertools, numpy as np, pandas as pd
from mk import ts
from common import D, load
import ev_engine as E, nx_feat
CAP = int(os.environ.get("CAP", 12))
NM = E.EV_NAMES + nx_feat.NAMES
Xs, Ys, Ts, FA, TF, SD, SY = [], [], [], [], [], [], []
need = [NM.index(n) for n in ("dd_e200", "w_e21", "rs168", "d_pos365", "adx", "atr_pct", "vol_z", "d_e200")]
for k, fn in enumerate(sorted(glob.glob(f"{D}/ev/*.npz"))):
    z = np.load(fn)
    m = z["tf"] >= 4
    Xs.append(z["X"][m][:, need]); Ys.append(z["Y"][m]); Ts.append(z["t"][m]); FA.append(z["fam"][m]); TF.append(z["tf"][m]); SD.append(z["side"][m]); SY.append(np.full(int(m.sum()), k))
X = np.concatenate(Xs); Y = np.concatenate(Ys); T = np.concatenate(Ts); FA = np.concatenate(FA); TF = np.concatenate(TF); SD = np.concatenate(SD); SY = np.concatenate(SY)
DD200, WE21, RS7, POS365, ADX, ATRP, VOLZ = (X[:, i] for i in range(7))
br = pd.read_pickle(f"{D}/breadth.pkl"); bt = br.index.values + 86400
k = np.searchsorted(bt, T, side="right") - 1
A200 = np.where(k >= 0, br["above200"].values[np.maximum(k, 0)], 0.5)
b1 = load("BTCUSDT"); dcl = {}
for c in b1:
    dcl[c["time"] // 86400] = c["close"]
days = np.array(sorted(dcl)); cl = np.array([dcl[d] for d in days])
s200 = np.array([cl[max(0, i - 199):i + 1].mean() for i in range(len(cl))])
kk = np.searchsorted((days + 1) * 86400, T, side="right") - 1
BTCUP = cl[np.maximum(kk, 0)] > s200[np.maximum(kk, 0)]
S = SD
G = {"btc": np.where(S > 0, BTCUP, ~BTCUP), "own200": S * DD200 > 0, "week": S * WE21 > 0, "rs": S * RS7 > 0,
     "breadth": np.where(S > 0, A200 > 0.5, A200 < 0.4), "adx25": ADX > 25, "vol": VOLZ > 1.0, "longonly": S > 0}
YRS = (2021, 2022, 2023, 2024, 2025)
YM = {y: (T >= ts(y)) & (T < (ts(y + 1) if y < 2025 else ts(2027))) for y in YRS}
def wk(y):
    return ((ts(y + 1) if y < 2025 else ts(2026, 10)) - ts(y)) / (7 * 86400)
def replay(idx, r, j):
    o = idx[np.argsort(T[idx], kind="stable")]
    busy, act, out = {}, [], []
    for i in o:
        t = T[i]; key = (SY[i], SD[i])
        if busy.get(key, 0) > t or r[i] != r[i]:
            continue
        act = [a for a in act if a[0] > t]
        if CAP and sum(1 for a in act if a[1] == SD[i]) >= CAP:
            continue
        end = t + int(j[i]) * TF[i] * 3600
        busy[key] = end; act.append((end, SD[i]))
        out.append((end, float(r[i])))
    return out
gate_sets = [()] + [(g,) for g in G] + [c for c in itertools.combinations(["btc", "own200", "week", "rs", "breadth", "adx25", "vol"], 2)] + \
            [c for c in itertools.combinations(["btc", "own200", "week", "rs", "breadth"], 3)]
FAMS = ["donch20", "donch55", "rangebrk", "bigcandle", "pullback", "squeeze", "retest"]
EXS = ["dc20", "dc50", "ch5", "ch8", "t8", "t12", "t20"]
res = []
for f in FAMS:
    fi = E.FAMS.index(f)
    for h in (4, 24):
        base0 = (FA == fi) & (TF == h)
        for si, sk in enumerate(E.STOPS):
            for ex in EXS:
                xi = E.EXITS.index(ex)
                r = Y[:, si, xi, 0].astype(float); j = Y[:, si, xi, 1]
                r = np.where(np.abs(r) > 80, np.nan, r)
                for gs in gate_sets:
                    m = base0.copy()
                    for g in gs:
                        m &= G[g]
                    per = []
                    for y in YRS:
                        idx = np.where(m & YM[y])[0]
                        out = sorted(replay(idx, r, j)) if len(idx) else []
                        rs = np.array([o[1] for o in out])
                        if len(rs) >= 10:
                            c = np.cumsum(rs); dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], c])) - np.concatenate([[0], c])))
                            per.append((rs.mean(), len(rs) / wk(y), dd))
                        else:
                            per.append((np.nan, len(rs) / wk(y), 0))
                    tr = [p[0] for p in per[:3]]
                    score = np.nanmin(tr) if not any(np.isnan(tr)) else -9
                    res.append((score, f, h, sk, ex, "+".join(gs) or "—", per))
    print("done", f, flush=True)
res.sort(key=lambda r: -r[0])
import pickle; pickle.dump(res, open(f"{D}/ev_gates.pkl", "wb"))
print("== лучшие по худшему году 2021–23 (выбор только по ним); 2024 и 2025–26 — проверка ==")
for sc, f, h, sk, ex, gs, per in res[:50]:
    print(f"{f:9s} {h:2d}ч стоп {sk} {ex:4s} | {gs:22s} || " + " | ".join(f"{y}: {p[0]:+.2f}R×{p[1]:.1f}/нед dd{p[2]:.0f}" for y, p in zip(YRS, per)), flush=True)
