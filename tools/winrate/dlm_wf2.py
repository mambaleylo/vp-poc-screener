"""⚡ walk-forward variants — how long the models learn and how often they are retrained (the user: "не проверяли ли мы
раньше период обучения?" — P/R took 24 months quarterly in v0.99.636, ⚡ was never checked): dlm_wf.py's recipe with NS
seeds x 2 feature sets, the train coins' orders closed 3 days before the period, within the last W months (0 = all
history), retrained every P months from 2023; the period's threshold = q0.99 of the train coins' out-of-sample scores
of the 365 days before it (in-sample scores of the period's own model when fewer than 1000 — the first year).
usage: dlm_wf2.py NAME W P [NS] -> <LABSTORE>/wf/var_<NAME>/scores_<stream>.npz (as dlm_wf.py's)"""
import sys, os, json, time, calendar, numpy as np, lightgbm as lgb, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
NAME, W, PM = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]); NS = int(sys.argv[4]) if len(sys.argv) > 4 else 1
ts = lambda y, m=1, d=1: calendar.timegm((y, m, d, 0, 0, 0))
from common import V
C = json.load(open(f"{ST}/feat_coins.json"))
def bn(gs):
    b = gs.replace("_USDT", "")
    for c in (b + "USDT", "1000" + b + "USDT"):
        if c in C["base"] or c in C["new"]: return c
r127 = sorted({bn(c) for c in V.RESEARCH_COINS_127 if bn(c)}); check = set(r127[2::3]); train = set(r127) - check
GROUP = {c: ("train" if c in train else "check" if c in check else "base" if c in C["base"] else "new") for c in C["base"] + C["new"]}
pr = dict(n_estimators=300, learning_rate=0.05, num_leaves=63, min_child_samples=1000, subsample=0.7, subsample_freq=1,
          colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
OUT = f"{ST}/wf/var_{NAME}"; os.makedirs(OUT, exist_ok=True)
PERIODS = []
y, m = 2023, 1
while (y, m) < (2026, 11):
    a = ts(y, m); m2 = m + PM; y2 = y + (m2 - 1) // 12; m2 = (m2 - 1) % 12 + 1; PERIODS.append((a, ts(y2, m2))); y, m = y2, m2
for stream in ("wick4h", "close2h"):
    rows = {k: [] for k in ("coin", "t", "side", "F", "R", "t1h", "fill", "tout", "kind", "lv", "atr")}
    for c, g in GROUP.items():
        fn = f"{ST}/feat/{stream}/{c}.npz"
        if not os.path.exists(fn): continue
        z = np.load(fn)
        if not len(z["t"]): continue
        rows["coin"].append(np.full(len(z["t"]), c))
        for k in ("t", "side", "F", "R", "t1h", "fill", "tout", "kind", "lv", "atr"): rows[k].append(z[k])
    D = {k: np.concatenate(v) for k, v in rows.items()}
    grp = np.array([GROUP[c] for c in D["coin"]]); TR = grp == "train"
    T = D["t"]; yv = np.clip(D["R"], -1.5, 1.5); F = D["F"]
    SC = np.full(len(T), np.nan); THR = np.full(len(T), np.inf); t0 = time.time()
    for a, b in PERIODS:
        tr = TR & (D["tout"] < a - 3 * 86400)
        if W: tr &= T >= a - W * 30.44 * 86400
        tr = np.flatnonzero(tr); te = np.flatnonzero((T >= a) & (T < b))
        if not len(te): continue
        ref = np.flatnonzero(TR & (T >= a - 365 * 86400) & (T < a))
        acc_te = np.zeros(len(te)); acc_ref = np.zeros(len(ref)); k = 0
        for X in (F[:, :28], F):
            for seed in range(NS):
                mdl = lgb.LGBMRegressor(random_state=seed, **pr).fit(X[tr], yv[tr])
                acc_te += mdl.predict(X[te]); acc_ref += mdl.predict(X[ref]) if len(ref) else 0; k += 1
        SC[te] = acc_te / k
        oos = ref[np.isfinite(SC[ref])]
        thr = float(np.quantile(SC[oos] if len(oos) >= 1000 else acc_ref / k, 0.99)); THR[te] = thr
        print(NAME, stream, time.strftime("%Y-%m", time.gmtime(a)), "train", len(tr), "test", len(te), "thr", round(thr, 4), f"{time.time() - t0:.0f}s", flush=True)
    np.savez_compressed(f"{OUT}/scores_{stream}.npz", coin=D["coin"], t=T, side=D["side"], score=SC, thr=THR, R=D["R"], t1h=D["t1h"],
                        fill=D["fill"], tout=D["tout"], kind=D["kind"], lv=D["lv"], atr=D["atr"], grp=grp)
print("done", NAME, flush=True)
