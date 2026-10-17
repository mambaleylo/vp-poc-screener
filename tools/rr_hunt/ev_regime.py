"""trend families on 4h / 1d with a market-regime gate (no model): longs only in a bull market, shorts only in a
bear one; one trade per coin & side until its exit, at most CAP per side; picked on 2021–23, judged on 2024 / 2025–26"""
import glob, os, numpy as np, pandas as pd
from mk import ts
from common import D, load
import ev_engine as E
CAP = int(os.environ.get("CAP", 12))
Ys, Ts, FA, TF, SD, SY = [], [], [], [], [], []
for k, fn in enumerate(sorted(glob.glob(f"{D}/ev/*.npz"))):
    z = np.load(fn)
    m = z["tf"] >= 4
    Ys.append(z["Y"][m]); Ts.append(z["t"][m]); FA.append(z["fam"][m]); TF.append(z["tf"][m]); SD.append(z["side"][m]); SY.append(np.full(int(m.sum()), k))
Y = np.concatenate(Ys); T = np.concatenate(Ts); FA = np.concatenate(FA); TF = np.concatenate(TF); SD = np.concatenate(SD); SY = np.concatenate(SY)
br = pd.read_pickle(f"{D}/breadth.pkl"); bt = br.index.values + 86400
k = np.searchsorted(bt, T, side="right") - 1
A50 = np.where(k >= 0, br["above50"].values[np.maximum(k, 0)], 0.5)
A200 = np.where(k >= 0, br["above200"].values[np.maximum(k, 0)], 0.5)
b1 = load("BTCUSDT"); dcl = {}
for c in b1:
    dcl[c["time"] // 86400] = c["close"]
days = np.array(sorted(dcl)); cl = np.array([dcl[d] for d in days])
s200 = np.array([cl[max(0, i - 199):i + 1].mean() for i in range(len(cl))])
kk = np.searchsorted((days + 1) * 86400, T, side="right") - 1
BTC_UP = cl[np.maximum(kk, 0)] > s200[np.maximum(kk, 0)]
GATES = {"без фильтра": np.ones(len(T), bool),
         "BTC выше/ниже 200д": np.where(SD > 0, BTC_UP, ~BTC_UP),
         "ширина рынка >0.5/<0.5 (выше EMA50)": np.where(SD > 0, A50 > 0.5, A50 < 0.5),
         "BTC 200д + ширина 200 >0.5/<0.4": np.where(SD > 0, BTC_UP & (A200 > 0.5), ~BTC_UP & (A200 < 0.4)),
         "только лонг, BTC выше 200д": (SD > 0) & BTC_UP}
YRS = (2021, 2022, 2023, 2024, 2025)
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
res = []
for fi, f in enumerate(E.FAMS):
    if f in ("mrext", "amd", "sweep"):
        continue
    for h in (4, 24):
        for gname, g in GATES.items():
            base = (FA == fi) & (TF == h) & g
            for si, sk in enumerate(E.STOPS):
                for xi, ex in enumerate(E.EXITS):
                    r = Y[:, si, xi, 0].astype(float); j = Y[:, si, xi, 1]
                    r = np.where(np.abs(r) > 80, np.nan, r)
                    per = []
                    for y in YRS:
                        m = base & (T >= ts(y)) & (T < (ts(y + 1) if y < 2025 else ts(2027)))
                        out = sorted(replay(np.where(m)[0], r, j))
                        rs = np.array([o[1] for o in out])
                        if len(rs):
                            c = np.cumsum(rs); dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], c])) - np.concatenate([[0], c])))
                            per.append((rs.mean(), len(rs) / wk(y), dd, (rs > 0).mean() * 100))
                        else:
                            per.append((np.nan, 0, 0, 0))
                    train = [p[0] for p in per[:3]]
                    res.append((np.nanmin(train) if all(p[1] > 0.3 for p in per[:3]) else -9, f, h, gname, sk, ex, per))
res.sort(key=lambda r: -r[0])
print("== лучшие по худшему году 2021–23 (выбор только по ним); проверка 2024 и 2025–26 ==")
for mn, f, h, gname, sk, ex, per in res[:40]:
    print(f"{f:9s} {h:2d}ч | {gname:32s} | стоп {sk} {ex:5s} || " + " | ".join(f"{y}: {p[0]:+.2f}R×{p[1]:.1f}/нед dd{p[2]:.0f}" for y, p in zip(YRS, per)))
