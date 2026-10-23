"""the deployed ⚡ recipe for any 4h family: 10 seeds on the engine's 28 features + 10 with the 5 daily ones, their mean;
yearly walk-forward on the 127's train coins, the threshold = q of the previous year's mean scores; trades on the 42
check coins, the 83 new ones, all unseen, the last 12 months. usage: s26_mix.py DIR FAM EXIT [NSEED]
s27: the same, trained on the v0.99.690 exit's labels (newlabel.py -> newlab_<dir>/) -> s27_<DIR>_<FAM>.npz"""
import sys; AV = list(sys.argv)
import os
import glob, numpy as np, lightgbm as lgb, warnings; warnings.filterwarnings("ignore")
from s15_wf import load, select, report, fmt
from mk import ts
import importlib
DR, FAM, EX = AV[1], AV[2], int(AV[3]); NS = int(AV[4]) if len(AV) > 4 else 10
os.environ.setdefault("TFH", {"s19h": "1", "s21h2": "2"}.get(DR, "4"))
E = importlib.import_module({"s20h4": "s20h4_engine", "s19h": "s19h_engine", "s21h2": "s21h2_engine"}.get(DR, "s23_engine"))
fi = E.FAMS.index(FAM)
a = load(DR, [fi]); b = load(DR + "x", [fi]); n0 = len(a["names"]); D = {}
for k in a:
    if k == "names": continue
    ax = 1 if k in ("R", "K", "W") else 0
    D[k] = np.concatenate([a[k], (b[k] + n0 if k == "sym" else (np.zeros_like(b[k]) if k == "chk" else b[k]))], axis=ax)
D["names"] = a["names"] + b["names"]; D["new"] = np.r_[np.zeros(len(a["t"]), bool), np.ones(len(b["t"]), bool)]
D["usdc"] = np.array([D["names"][k] == "USDCUSDT" for k in D["sym"]])
F2, t2 = [], []
for d in (DR, DR + "x"):
    for f in sorted(glob.glob(f"{d}/*.npz")):
        z = np.load(f); m = z["fam"] == fi
        if not m.any(): continue
        g = np.load(f"f2_{d}/{os.path.basename(f)}"); F2.append(g["F2"][m]); t2.append(g["t"][m])
F2 = np.concatenate(F2); t2 = np.concatenate(t2); assert (t2 == D["t"]).all()
T = D["t"]; TR = ~D["chk"] & ~D["new"]
YN = np.concatenate([np.load(f"newlab_{d}/{os.path.basename(f)}")["R"] for d in (DR, DR + "x") for f in sorted(glob.glob(f"{d}/*.npz"))
                     if (np.load(f)["fam"] == fi).any()]).astype(float)
assert len(YN) == len(T), (len(YN), len(T))
TR &= np.isfinite(YN); y = np.clip(np.nan_to_num(YN), -1.5, 1.5)
pr = dict(n_estimators=300, learning_rate=0.05, num_leaves=63, min_child_samples=1000, subsample=0.7, subsample_freq=1,
          colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
SC = np.zeros(len(T)); cnt = np.zeros(len(T)); REF = {}
for X in (D["F"], np.concatenate([D["F"], F2[:, [0, 1, 2, 5, 8]]], axis=1)):
    for seed in range(NS):
        rng = np.random.default_rng(seed)
        for Y in (2022, 2023, 2024, 2025, 2026):
            tr = np.flatnonzero(TR & (T < ts(Y) - 3 * 86400))
            if len(tr) < 20000: continue
            if len(tr) > 800000: tr = rng.choice(tr, 800000, replace=False)
            m = lgb.LGBMRegressor(random_state=seed, **pr).fit(X[tr], y[tr])
            te = (T >= ts(Y)) & (T < ts(Y + 1)); ref = TR & (T >= ts(Y - 1)) & (T < ts(Y))
            SC[te] += m.predict(X[te]); cnt[te] += 1
            REF.setdefault(Y, [ref, np.zeros(int(ref.sum()))])[1] += m.predict(X[ref]) if ref.any() else 0
SC = np.where(cnt > 0, SC / np.maximum(cnt, 1), np.nan)
THR = {}
for Y, (ref, acc) in REF.items():
    prev = ref & np.isfinite(SC)
    THR[Y] = SC[prev] if prev.sum() >= 1000 else acc / (2 * NS)
np.savez(f"s27_{DR}_{FAM}.npz", SC=SC, THR=np.array(THR, dtype=object))
raise SystemExit
def last12(sel):
    sel = sel[T[sel] >= ts(2025, 10)]
    return f"посл.12м n{len(sel)} WR {D['W'][EX][sel].mean()*100:.0f}% {D['R'][EX][sel].mean():+.3f}R" if len(sel) else "—"
for q in (0.985, 0.99):
    for nm, sub in (("пров42", D["chk"]), ("новые83", D["new"] & ~D["usdc"]), ("невид125", (D["chk"] | D["new"]) & ~D["usdc"])):
        s_ = select(D, EX, SC, THR, q, 20, sub)
        print(f"{DR} {FAM:6s} E{EX} q{q} {nm:8s}: {fmt(report(D, EX, s_))} | {last12(s_)}", flush=True)
