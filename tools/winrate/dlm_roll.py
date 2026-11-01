"""⚡ (the user: "проверь, не лучше ли плавающее годовое окно обучения для каждого последующего месяца"): the deployed recipe
(s26_mix: the 28 features + the 28 + 5 daily ones, LightGBM, the train coins, events closed 3 days before the period) retrained
by VARIANT: Y = all history, once a year (the bot now); M0 = all history, every month; M12 / M24 = the last 12 / 24 months,
every month. NS seeds per feature set (default 1: 2 models a period). Out-of-sample scores 2023-01 .. 2026-10 of every coin
-> <DR>_roll_<FAM>_<EX>_<VAR>.npz. usage: dlm_roll.py DR FAM EX VAR [NS]"""
import sys; AV = list(sys.argv)
import os, glob, calendar, numpy as np, lightgbm as lgb, warnings; warnings.filterwarnings("ignore")
from s15_wf import load
DR, FAM, EX, VAR = AV[1], AV[2], int(AV[3]), AV[4]; NS = int(AV[5]) if len(AV) > 5 else 1
os.environ.setdefault("TFH", {"s21h2": "2"}.get(DR.split("_")[0], "4"))
import importlib
E = importlib.import_module("s21h2_engine" if DR.startswith("s21h2") else "s23_engine")
fi = E.FAMS.index(FAM)
ts = lambda y, m=1, d=1: calendar.timegm((y, m, d, 0, 0, 0))
D = load(DR, [fi]); F2 = []
for f in sorted(glob.glob(f"{DR}/*.npz")):
    z = np.load(f); m = z["fam"] == fi
    if m.any(): F2.append(np.load(f"f2_{DR}/{os.path.basename(f)}")["F2"][m])
F2 = np.concatenate(F2); T = D["t"]; TR = ~D["chk"]; y = np.clip(D["R"][EX], -1.5, 1.5)
XS = (D["F"], np.concatenate([D["F"], F2[:, [0, 1, 2, 5, 8]]], axis=1))
pr = dict(n_estimators=300, learning_rate=0.05, num_leaves=63, min_child_samples=1000, subsample=0.7, subsample_freq=1,
          colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
P = []
if VAR == "Y":
    P = [(ts(Y), ts(Y + 1) if Y < 2026 else ts(2026, 11)) for Y in (2022, 2023, 2024, 2025, 2026)]
else:
    yy, mm = 2022, 1
    while (yy, mm) < (2026, 11):
        a = ts(yy, mm); yy, mm = (yy + 1, 1) if mm == 12 else (yy, mm + 1); P.append((a, ts(yy, mm)))
W = 0 if VAR in ("Y", "M0") else int(VAR[1:])
SC = np.full(len(T), np.nan); INS = np.full(len(T), np.nan)   # INS: the period's model on its year before (the first threshold)
out = f"{DR}_roll_{FAM}_{EX}_{VAR}.npz"
for k, (a, b) in enumerate(P):
    tr = TR & (T < a - 3 * 86400)
    if W: tr &= T >= a - 3 * 86400 - W * 30.4 * 86400
    tr = np.flatnonzero(tr)
    if len(tr) < 20000: continue
    te = (T >= a) & (T < b)
    if not te.any(): continue   # past the data's end
    s = np.zeros(int(te.sum())); ref = TR & (T >= a - 365 * 86400) & (T < a); si = np.zeros(int(ref.sum()))
    for X in XS:
        for seed in range(NS):
            m = lgb.LGBMRegressor(random_state=seed, **pr).fit(X[tr], y[tr]); s += m.predict(X[te]); si += m.predict(X[ref]) if k == 0 else 0
    SC[te] = s / (2 * NS)
    if k == 0: INS[ref] = si / (2 * NS)
    print(f"{VAR} {np.datetime64(a, 's')}: обучено на {len(tr)}", flush=True)
np.savez(out, SC=SC, INS=INS)
print("roll done", VAR, flush=True)
