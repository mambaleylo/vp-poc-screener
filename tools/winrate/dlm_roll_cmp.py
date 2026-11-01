"""dlm_roll.py's variants side by side: per month the threshold = q of the variant's own out-of-sample scores of the train coins
over the 365 days before (the first period's in-sample ones while short), every order above it, one per coin & side until
its exit, at most 20 a side -> 2023-01 .. 2026-10 on the train coins (out of time) and the check coins (never seen): trades a
month, R, sum, drawdown, R by year. usage: dlm_roll_cmp.py DR FAM EX [Q]"""
import sys; AV = list(sys.argv)
import os, glob, calendar, numpy as np
from s15_wf import load
DR, FAM, EX = AV[1], AV[2], int(AV[3]); Q = float(AV[4]) if len(AV) > 4 else 0.99
os.environ.setdefault("TFH", {"s21h2": "2"}.get(DR.split("_")[0], "4"))
import importlib
E = importlib.import_module("s21h2_engine" if DR.startswith("s21h2") else "s23_engine")
ts = lambda y, m=1, d=1: calendar.timegm((y, m, d, 0, 0, 0))
D = load(DR, [E.FAMS.index(FAM)]); T, S, SYM, K, R = D["t"], D["side"], D["sym"], D["K"][EX], D["R"][EX]; TR = ~D["chk"]
def pool(SC, INS, sub):
    thr = np.full(len(T), np.inf); yy, mm = 2023, 1
    while (yy, mm) < (2026, 11):
        a = ts(yy, mm); yy, mm = (yy + 1, 1) if mm == 12 else (yy, mm + 1); b = ts(yy, mm)
        ref = TR & (T >= a - 365 * 86400) & (T < a); v = SC[ref & np.isfinite(SC)]
        if len(v) < 1000: v = np.r_[v, INS[ref & np.isfinite(INS)]]
        thr[(T >= a) & (T < b)] = np.quantile(v, Q)
    idx = np.flatnonzero(sub & np.isfinite(SC) & (SC >= thr) & (T >= ts(2023)))
    o = idx[np.lexsort((-SC[idx], T[idx]))]; busy = {}; act = []; out = []
    for i in o:
        t = T[i]; key = (SYM[i], S[i])
        if busy.get(key, 0) > t: continue
        act = [x for x in act if x[0] > t]
        if sum(1 for x in act if x[1] == S[i]) >= 20: continue
        end = t + int(K[i]) * 3600; busy[key] = end; act.append((end, S[i])); out.append(i)
    return np.array(out, np.int64)
def st(sel):
    r = R[sel]; t = T[sel]; o = np.argsort(t); c = np.cumsum(r[o]); dd = float(np.max(np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c]))
    yrs = " ".join(f"{Y}: {r[(t >= ts(Y)) & (t < ts(Y + 1))].mean():+.3f}" for Y in (2023, 2024, 2025, 2026))
    return f"{len(sel) / 46:5.1f}/мес {r.mean():+.3f}R Σ{r.sum():+6.0f}R просадка {dd:4.0f}R | {yrs}"
print(f"{DR} {FAM} E{EX} q{Q}", flush=True)
for v in ("Y", "M0", "M12", "M24"):
    fn = f"{DR}_roll_{FAM}_{EX}_{v}.npz"
    if not os.path.exists(fn): continue
    z = np.load(fn); SC, INS = z["SC"], z["INS"]
    for nm, sub in (("обуч. монеты", TR), ("новые монеты", ~TR)):
        print(f"{ {'Y': 'как в боте (вся история, раз в год)', 'M0': 'вся история, каждый месяц', 'M12': '12 мес, каждый месяц', 'M24': '24 мес, каждый месяц'}[v]:38s} {nm}: {st(pool(SC, INS, sub))}", flush=True)
print("cmp done", flush=True)
