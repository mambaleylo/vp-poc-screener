"""the 2022 stress test's ⚡ orders: 2022 (the bear market) has too little history before it to train on, so the models
learn the train coins' filled orders of 2023-2026 (dlm_allorders.py's recipe, NS seeds x 2 feature sets) and score every
2022 order of the bot's coins (out of sample backwards in time); the threshold = q0.99 of the train coins' 2022 filled
orders' scores (the level only). -> <LABSTORE>/wf/allorders_<stream>_y2022.npz"""
import sys, os, json, time, calendar, numpy as np, lightgbm as lgb, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlm_engine as DE
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store"); NS = 3
ts = lambda y, m=1, d=1: calendar.timegm((y, m, d, 0, 0, 0))
from common import V
C = json.load(open(f"{ST}/feat_coins.json"))
def bn(gs):
    b = gs.replace("_USDT", "")
    for c in (b + "USDT", "1000" + b + "USDT"):
        if c in C["base"] or c in C["new"]: return c
r127 = sorted({bn(c) for c in V.RESEARCH_COINS_127 if bn(c)}); check = set(r127[2::3]); train = set(r127) - check
pr = dict(n_estimators=300, learning_rate=0.05, num_leaves=63, min_child_samples=1000, subsample=0.7, subsample_freq=1,
          colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
M = json.load(open("/home/user/vp-poc-screener/vp_dlm_model.json")); S = {s["name"]: s for s in M["streams"]}
for stream in ("wick4h", "close2h"):
    F, y, T = [], [], []
    for c in train:
        z = np.load(f"{ST}/feat/{stream}/{c}.npz")
        if len(z["t"]): F.append(z["F"]); y.append(np.clip(z["R"], -1.5, 1.5)); T.append(z["t"])
    F = np.concatenate(F); y = np.concatenate(y); T = np.concatenate(T); t0 = time.time()
    tr = T >= ts(2023) + 3 * 86400; ref = (T >= ts(2022)) & (T < ts(2023))
    ms = [(X_, lgb.LGBMRegressor(random_state=sd, **pr).fit(F[tr][:, :X_], y[tr])) for X_ in (28, 33) for sd in range(NS)]
    thr = float(np.quantile(np.mean([m.predict(F[ref][:, :X_]) for X_, m in ms], axis=0), 0.99))
    print(stream, "train", int(tr.sum()), "thr 2022", round(thr, 4), f"{time.time() - t0:.0f}s", flush=True)
    st = S[stream]; p = DE.STREAMS[stream]; bs = p["hh"] * 3600; B = DE.btc_ctx(stream)
    out = {k: [] for k in ("coin", "t", "side", "lv", "atr", "score", "thr", "filled", "t1h", "fill", "R", "kind", "tout", "grp")}
    for c in C["base"]:
        h1 = DE.load1h(c); ev = DE.features(c, stream, B, h1)
        if ev is None: continue
        tsc = ev["t"] + bs; ii = np.flatnonzero((tsc >= ts(2022)) & (tsc < ts(2023)))
        if not len(ii): continue
        sc = np.mean([m.predict(ev["f"][ii][:, :X_]) for X_, m in ms], axis=0); k = sc >= thr; ii = ii[k]; sc = sc[k]
        if not len(ii): continue
        T1, O1, H1, L1, C1, V1 = h1
        fl, t1h, fill, R, kind, tout = DE.fill_walk(T1, O1, H1, L1, C1, tsc[ii], ev["side"][ii].astype(np.int64), ev["lv"][ii], ev["atr"][ii], bs, p["ch"],
                                                    DE.ALIVE, DE.HOLD, st["take_atr"], st["stop_atr"], st["hard_stop_atr"], DE.FEE_IN, DE.FEE_TAKE, DE.FEE_OUT, DE.FUND)
        for key, v in (("coin", np.full(len(ii), c)), ("t", tsc[ii]), ("side", ev["side"][ii]), ("lv", ev["lv"][ii]), ("atr", ev["atr"][ii]), ("score", sc),
                       ("thr", np.full(len(ii), thr)), ("filled", fl), ("t1h", t1h), ("fill", fill), ("R", R), ("kind", kind), ("tout", tout), ("grp", np.full(len(ii), "base"))):
            out[key].append(v)
    O = {k: np.concatenate(v) for k, v in out.items()}
    np.savez_compressed(f"{ST}/wf/allorders_{stream}_y2022.npz", **O)
    r = O["R"][O["filled"]]
    print(stream, "2022 orders", len(O["t"]), "filled", int(O["filled"].sum()), f"R {r.mean():+.3f} WR {(r > 0).mean() * 100:.0f}%", f"{time.time() - t0:.0f}s", flush=True)
print("done", flush=True)
