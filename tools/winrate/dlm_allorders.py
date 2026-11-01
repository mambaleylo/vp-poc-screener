"""every ⚡ order the bot would make on its coins 2023-2026 — the filled AND the never-filled ones (the pool keeps only the
filled; an armed limit that never fills holds room too): dlm_wf.py's yearly models (all history, NS seeds x 2 feature sets,
trained on the train coins' filled orders) score every order of the coin (dlm_engine.features), the ones >= the year's
threshold kept with their fill (dlm_engine.fill_walk, the model file's exits). -> <LABSTORE>/wf/allorders_<stream>.npz
usage: dlm_allorders.py [NS]"""
import sys, os, json, time, calendar, numpy as np, lightgbm as lgb, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlm_engine as DE
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store"); NS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
QK = float(sys.argv[2]) if len(sys.argv) > 2 else 0.99   # keep the orders >= this quantile's threshold (the bot's 0.99 stays "thr")
SUF = ("" if QK == 0.99 else f"_q{QK}") + os.environ.get("OUTSUF", "")
FEAT = os.environ.get("FEATDIR", "feat")   # the labels' folder (feat_<tag>: dlm_relabel.py)
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
M = json.load(open("/home/user/vp-poc-screener/vp_dlm_model.json")); S = {s["name"]: s for s in M["streams"]}
YEARS = range(2023, 2027)
for stream in ("wick4h", "close2h"):
    rows = {k: [] for k in ("coin", "t", "F", "R", "tout")}
    for c, g in GROUP.items():
        if g != "train": continue
        z = np.load(f"{ST}/{FEAT}/{stream}/{c}.npz")
        if not len(z["t"]): continue
        rows["coin"].append(np.full(len(z["t"]), c))
        for k in ("t", "F", "R", "tout"): rows[k].append(z[k])
    D = {k: np.concatenate(v) for k, v in rows.items()}; y = np.clip(D["R"], -1.5, 1.5); t0 = time.time()
    MODELS, THR = {}, {}
    prev = None
    for Y in [2022] + list(YEARS):
        tr = np.flatnonzero(D["tout"] < ts(Y) - 3 * 86400)
        if len(tr) < 20000: continue
        ms = [(X_, lgb.LGBMRegressor(random_state=sd, **pr).fit(D["F"][tr][:, :X_], y[tr])) for X_ in (28, 33) for sd in range(NS)]
        MODELS[Y] = ms
        ref = np.flatnonzero((D["t"] >= ts(Y - 1)) & (D["t"] < ts(Y)))
        sc_ref = np.mean([m.predict(D["F"][ref][:, :X_]) for X_, m in (MODELS.get(Y - 1) or ms)], axis=0)   # the previous year by its own model
        THR[Y] = float(np.quantile(sc_ref, 0.99)); THR[(Y, "keep")] = float(np.quantile(sc_ref, QK))
        print(stream, Y, "train", len(tr), "thr", round(THR[Y], 4), f"{time.time() - t0:.0f}s", flush=True)
    st = S[stream]; p = DE.STREAMS[stream]; bs = p["hh"] * 3600; B = DE.btc_ctx(stream)
    out = {k: [] for k in ("coin", "t", "side", "lv", "atr", "score", "thr", "filled", "t1h", "fill", "R", "kind", "tout", "grp")}
    for k, c in enumerate(C[os.environ.get("COINS", "base")]):   # COINS=new: the 226 new coins
        h1 = DE.load1h(c); ev = DE.features(c, stream, B, h1)
        if ev is None: continue
        tsc = ev["t"] + bs; yr = tsc.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970
        keep = np.zeros(len(tsc), bool); sc = np.full(len(tsc), np.nan); th = np.full(len(tsc), np.inf)
        for Y in YEARS:
            ii = np.flatnonzero(yr == Y)
            if not len(ii) or Y not in MODELS: continue
            sc[ii] = np.mean([m.predict(ev["f"][ii][:, :X_]) for X_, m in MODELS[Y]], axis=0); th[ii] = THR[Y]
        tk = np.array([THR.get((int(y_), "keep"), np.inf) for y_ in yr])
        keep = np.isfinite(sc) & (sc >= tk)
        ii = np.flatnonzero(keep)
        if not len(ii): continue
        T1, O1, H1, L1, C1, V1 = h1
        fl, t1h, fill, R, kind, tout = DE.fill_walk(T1, O1, H1, L1, C1, tsc[ii], ev["side"][ii].astype(np.int64), ev["lv"][ii], ev["atr"][ii], bs, p["ch"],
                                                    DE.ALIVE, DE.HOLD, st["take_atr"], st["stop_atr"], st["hard_stop_atr"], DE.FEE_IN, DE.FEE_TAKE, DE.FEE_OUT, DE.FUND)
        for key, v in (("coin", np.full(len(ii), c)), ("t", tsc[ii]), ("side", ev["side"][ii]), ("lv", ev["lv"][ii]), ("atr", ev["atr"][ii]), ("score", sc[ii]),
                       ("thr", th[ii]), ("filled", fl), ("t1h", t1h), ("fill", fill), ("R", R), ("kind", kind), ("tout", tout), ("grp", np.full(len(ii), GROUP.get(c, "new")))):
            out[key].append(v)
        if k % 50 == 0: print(stream, k, c, f"{time.time() - t0:.0f}s", flush=True)
    O = {k: np.concatenate(v) for k, v in out.items()}
    np.savez_compressed(f"{ST}/wf/allorders_{stream}{SUF}.npz", **O)
    print(stream, "orders", len(O["t"]), "filled", int(O["filled"].sum()), f"{time.time() - t0:.0f}s", flush=True)
