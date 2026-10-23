"""s23 walk-forward: yearly LightGBM per family (label = exit `lab`), trained on A) the 127's train coins or B) those plus
the 83 new coins; threshold = q of the previous year's out-of-sample train scores; trades (exit `ev`) reported on the 42
check coins (never trained on in either mode), the 83 new (mode A only) and the last 12 months
usage: s23_wf.py TFH fam[,fam] lab ev A|B"""
import sys; AV = list(sys.argv)
import numpy as np, lightgbm as lgb, warnings, os; warnings.filterwarnings("ignore")
os.environ["TFH"] = AV[1]
import s23_engine as E
from s15_wf import load, select, report, fmt
from mk import ts
TFH, fams, lab, ev, mode = int(AV[1]), AV[2].split(","), int(AV[3]), int(AV[4]), AV[5]
pr = dict(n_estimators=300, learning_rate=0.05, num_leaves=63, min_child_samples=1000, subsample=0.7, subsample_freq=1,
          colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
def merged(fi):
    a = load(f"s23_{TFH}h", [fi]); b = load(f"s23_{TFH}hx", [fi])
    n0 = len(a["names"]); D = {}
    for k in a:
        if k == "names": continue
        ax = 1 if k in ("R", "K", "W") else 0
        bb = b[k] + n0 if k == "sym" else (np.zeros_like(b[k]) if k == "chk" else b[k])
        D[k] = np.concatenate([a[k], bb], axis=ax)
    D["names"] = a["names"] + b["names"]
    D["new"] = np.r_[np.zeros(len(a["t"]), bool), np.ones(len(b["t"]), bool)]
    return D
import glob
def addf(D, use):
    F2 = np.concatenate([np.load(f)["F2"] for d in ("s24_4h", "s24_4hx") for f in sorted(glob.glob(f"{d}/*.npz"))])
    t2 = np.concatenate([np.load(f)["t"] for d in ("s24_4h", "s24_4hx") for f in sorted(glob.glob(f"{d}/*.npz"))])
    assert len(t2) == len(D["t"]) and (t2 == D["t"]).all()
    D["F"] = np.concatenate([D["F"], F2[:, use]], axis=1) if len(use) else D["F"]
def last12(D, e, sel):
    sel = sel[D["t"][sel] >= ts(2025, 10)]
    return (f"посл.12м n{len(sel)} WR {D['W'][e][sel].mean()*100:.0f}% {D['R'][e][sel].mean():+.3f}R") if len(sel) else "—"
for fam in fams:
    D = merged(E.FAMS.index(fam)); USE = [int(x) for x in AV[6].split(",")] if len(AV) > 6 and AV[6] else []
    addf(D, USE)
    T, F = D["t"], D["F"]
    TR = ~D["chk"] & (~D["new"] if mode == "A" else True)
    y = np.clip(D["R"][lab], -1.5, 1.5); rng = np.random.default_rng(int(os.environ.get("SEED", "0")))
    SC = np.full(len(T), np.nan); THR = {}
    for Y in (2022, 2023, 2024, 2025, 2026):
        tr = np.flatnonzero(TR & (T < ts(Y) - 3 * 86400))
        if len(tr) < 20000: continue
        if len(tr) > 800000: tr = rng.choice(tr, 800000, replace=False)
        m = lgb.LGBMRegressor(random_state=int(os.environ.get("SEED", "0")), **pr).fit(F[tr], y[tr])
        te = (T >= ts(Y)) & (T < ts(Y + 1)); ref = TR & (T >= ts(Y - 1)) & (T < ts(Y))
        need = te | ref; sc = np.full(len(T), np.nan); sc[need] = m.predict(F[need]); SC[te] = sc[te]
        prev = ref & np.isfinite(SC); THR[Y] = SC[prev] if prev.sum() >= 1000 else sc[ref]
    np.savez(f"s24_sc_{TFH}h_{fam}_{lab}_{mode}_{len(USE)}.npz", SC=SC, THR=np.array(THR, dtype=object))
    for q in (0.98, 0.99, 0.995):
        sets = [("пров42", D["chk"])] + ([("новые83", D["new"]), ("невид125", D["chk"] | D["new"])] if mode == "A" else [])
        for nm, sub in sets:
            s_ = select(D, ev, SC, THR, q, 12, sub)
            print(f"s{os.environ.get('SEED', '0')} +{AV[6] if len(AV) > 6 else ''}пр {TFH}ч {fam:5s} метка{lab} выход{ev} {mode} q{q} {nm:8s}: {fmt(report(D, ev, s_))} | {last12(D, ev, s_)}", flush=True)
