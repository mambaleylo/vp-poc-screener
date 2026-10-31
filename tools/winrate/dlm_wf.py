"""⚡ walk-forward v2 (the deployed recipe of s26_mix.py on the engine v2 events, <LABSTORE>/feat): per stream, for each year
2022..2026 LightGBM models (NS seeds x 2 feature sets: the 28 engine features, all 33) trained on the train coins' filled
orders closed 3 days before the year (the 127 research coins without every third — those are the check coins), the label
R clipped to +-1.5; the year's orders of every coin scored by them; the year's threshold = q of the previous year's scores
of the train coins. -> <LABSTORE>/wf/scores_<stream>.npz (per event: coin, t, side, score, thr) and the pool by the bot's
rules (pool.json: the first to fill of a coin & side wins, busy until its exit, 20 open a side, the nearer level first in
an hour). usage: dlm_wf.py [NS] [Q]"""
import sys, os, json, glob, time, calendar, numpy as np, lightgbm as lgb, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
NS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
Q = float(sys.argv[2]) if len(sys.argv) > 2 else 0.99
ts = lambda y, m=1, d=1: calendar.timegm((y, m, d, 0, 0, 0))
from common import V
C = json.load(open(f"{ST}/feat_coins.json"))
def bn(gs):
    b = gs.replace("_USDT", "")
    for c in (b + "USDT", "1000" + b + "USDT"):
        if c in C["base"] or c in C["new"]: return c
r127 = sorted({bn(c) for c in V.RESEARCH_COINS_127 if bn(c)})
check = set(r127[2::3]); train = set(r127) - check
GROUP = {c: ("train" if c in train else "check" if c in check else "base" if c in C["base"] else "new") for c in C["base"] + C["new"]}
pr = dict(n_estimators=300, learning_rate=0.05, num_leaves=63, min_child_samples=1000, subsample=0.7, subsample_freq=1,
          colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
os.makedirs(f"{ST}/wf", exist_ok=True)
for stream in ("wick4h", "close2h"):
    rows = {k: [] for k in ("coin", "t", "side", "F", "R", "t1h", "fill", "tout", "kind", "lv", "atr")}
    for c, g in GROUP.items():
        fn = f"{ST}/feat/{stream}/{c}.npz"
        if not os.path.exists(fn): continue
        z = np.load(fn)
        if not len(z["t"]): continue
        n = len(z["t"]); rows["coin"].append(np.full(n, c))
        for k in ("t", "side", "F", "R", "t1h", "fill", "tout", "kind", "lv", "atr"): rows[k].append(z[k])
    D = {k: np.concatenate(v) for k, v in rows.items()}
    grp = np.array([GROUP[c] for c in D["coin"]]); TR = grp == "train"
    T = D["t"]; y = np.clip(D["R"], -1.5, 1.5); F = D["F"]
    print(stream, "orders filled", len(T), "train", int(TR.sum()), flush=True)
    SC = np.full(len(T), np.nan); THR = {}
    t0 = time.time()
    for Y in range(2022, 2027):
        tr = np.flatnonzero(TR & (D["tout"] < ts(Y) - 3 * 86400))
        te = np.flatnonzero((T >= ts(Y)) & (T < ts(Y + 1))); ref = np.flatnonzero(TR & (T >= ts(Y - 1)) & (T < ts(Y)))
        if len(tr) < 20000 or not len(te):
            print(stream, Y, "skip: train", len(tr), flush=True); continue
        rng = np.random.default_rng(0)
        if len(tr) > 800000: tr = rng.choice(tr, 800000, replace=False)
        acc_te = np.zeros(len(te)); acc_ref = np.zeros(len(ref)); k = 0
        for X in (F[:, :28], F):
            for seed in range(NS):
                m = lgb.LGBMRegressor(random_state=seed, **pr).fit(X[tr], y[tr])
                acc_te += m.predict(X[te]); acc_ref += m.predict(X[ref]) if len(ref) else 0; k += 1
        SC[te] = acc_te / k
        prev = ref[np.isfinite(SC[ref])]
        base_ref = SC[prev] if len(prev) >= 1000 else acc_ref / k   # the previous year scored by its own year's model when it has one
        THR[Y] = float(np.quantile(base_ref, Q))
        print(stream, Y, "train", len(tr), "test", len(te), "thr", round(THR[Y], 4), f"{time.time() - t0:.0f}s", flush=True)
    yr = (T.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970)
    thr_ev = np.array([THR.get(int(v), np.inf) for v in yr])
    np.savez_compressed(f"{ST}/wf/scores_{stream}.npz", coin=D["coin"], t=T, side=D["side"], score=SC, thr=thr_ev, R=D["R"], t1h=D["t1h"],
                        fill=D["fill"], tout=D["tout"], kind=D["kind"], lv=D["lv"], atr=D["atr"], grp=grp)
    json.dump({"thr": THR, "ns": NS, "q": Q}, open(f"{ST}/wf/thr_{stream}.json", "w"))
print("done", flush=True)
