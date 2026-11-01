"""every ⚡ close2h order the bot would make 2023-2026 (dlm_allorders.py's output format), scored by models trained the way the
deployed one was — on the restored research engine's events (s21h2 fam d2, label E1, the 28 / 28 + 5 daily features, the train
coins), not on the bot-feature orders: VAR Y = retrained once a year on all history (the bot now), M0 = every month on all
history. Each period's threshold = q0.99 of the period-before models' scores of the train coins' bot orders over the 365 days
before (the first period: its own model). -> <LABSTORE>/wf/allorders_close2h_<VAR>.npz (money_arm2.orders(suf="_rsY") ...)
usage: dlm_allorders_rs.py VAR [NS]"""
import sys; AV = list(sys.argv)
import os, glob, json, time, calendar, numpy as np, lightgbm as lgb, warnings; warnings.filterwarnings("ignore")
VAR = AV[1]; NS = int(AV[2]) if len(AV) > 2 else 3
os.environ["TFH"] = "2"
import s21h2_engine as E, dlm_engine as DE
from s15_wf import load
from common import V
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store"); ts = lambda y, m=1, d=1: calendar.timegm((y, m, d, 0, 0, 0))
stream = "close2h"; MJ = json.load(open("/home/user/vp-poc-screener/vp_dlm_model.json")); S = [s for s in MJ["streams"] if s["name"] == stream][0]
# the research events (training)
fi = E.FAMS.index("d2"); D = load("s21h2", [fi]); F2 = []
for f in sorted(glob.glob("s21h2/*.npz")):
    z = np.load(f); m = z["fam"] == fi
    if m.any(): F2.append(np.load(f"f2_s21h2/{os.path.basename(f)}")["F2"][m])
X33 = np.concatenate([D["F"], np.concatenate(F2)[:, [0, 1, 2, 5, 8]]], axis=1); T = D["t"]; TR = ~D["chk"]; y = np.clip(D["R"][1], -1.5, 1.5)
pr = dict(n_estimators=300, learning_rate=0.05, num_leaves=63, min_child_samples=1000, subsample=0.7, subsample_freq=1, colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
if VAR == "Y":
    P = [(ts(Y), ts(Y + 1)) for Y in (2022, 2023, 2024, 2025, 2026)]
else:
    P = []; yy, mm = 2022, 1
    while (yy, mm) < (2026, 10):
        a = ts(yy, mm); yy, mm = (yy + 1, 1) if mm == 12 else (yy, mm + 1); P.append((a, ts(yy, mm)))
t0 = time.time(); MODELS = []
for a, b in P:
    tr = np.flatnonzero(TR & (T < a - 3 * 86400))
    MODELS.append([(X_, lgb.LGBMRegressor(random_state=sd, **pr).fit(X33[tr][:, :X_], y[tr])) for X_ in (28, 33) for sd in range(NS)])
    print(VAR, np.datetime64(a, "s"), "обучено на", len(tr), f"{time.time() - t0:.0f}s", flush=True)
# the bot's orders: the train coins' first (the thresholds), then every coin
C = json.load(open(f"{ST}/feat_coins.json"))
def bn(gs):
    b = gs.replace("_USDT", "")
    for c in (b + "USDT", "1000" + b + "USDT"):
        if c in C["base"] or c in C["new"]: return c
r127 = sorted({bn(c) for c in V.RESEARCH_COINS_127 if bn(c)}); check = set(r127[2::3]); train = set(r127) - check
GROUP = {c: ("train" if c in train else "check" if c in check else "base" if c in C["base"] else "new") for c in C["base"] + C["new"]}
p = DE.STREAMS[stream]; bs = p["hh"] * 3600; B = DE.btc_ctx(stream)
def score(ev, tsc):
    """each order by its period's model (cur) and the period before's (prev, for the threshold)"""
    cur = np.full(len(tsc), np.nan); prev = np.full(len(tsc), np.nan); per = np.full(len(tsc), -1)
    for k, (a, b) in enumerate(P):
        ii = np.flatnonzero((tsc >= a) & (tsc < b))
        if not len(ii): continue
        per[ii] = k; cur[ii] = np.mean([m.predict(ev["f"][ii][:, :X_]) for X_, m in MODELS[k]], axis=0)
    return cur, per
EVS = {}
for c in C["base"]:
    h1 = DE.load1h(c); ev = DE.features(c, stream, B, h1)
    if ev is None: continue
    tsc = ev["t"] + bs; cur, per = score(ev, tsc); EVS[c] = (h1, ev, tsc, cur, per)
print("оценены ордера", len(EVS), "монет", f"{time.time() - t0:.0f}s", flush=True)
# thresholds: q0.99 of the train coins' order scores over the 365 days before each period (the scores of the models of their own periods)
allt = np.concatenate([v[2] for c, v in EVS.items() if GROUP.get(c) == "train"]); alls = np.concatenate([v[3] for c, v in EVS.items() if GROUP.get(c) == "train"])
THR = []
for k, (a, b) in enumerate(P):
    m = (allt >= a - 365 * 86400) & (allt < a) & np.isfinite(alls)
    if m.sum() < 5000: m = (allt >= a) & (allt < b) & np.isfinite(alls)   # the first period: its own
    THR.append(float(np.quantile(alls[m], 0.99)))
out = {k: [] for k in ("coin", "t", "side", "lv", "atr", "score", "thr", "filled", "t1h", "fill", "R", "kind", "tout", "grp")}
for c, (h1, ev, tsc, cur, per) in EVS.items():
    th = np.array([THR[k] if k >= 0 else np.inf for k in per]); ii = np.flatnonzero(np.isfinite(cur) & (cur >= th) & (tsc >= ts(2023)))
    if not len(ii): continue
    T1, O1, H1, L1, C1, V1 = h1
    fl, t1h, fill, R, kind, tout = DE.fill_walk(T1, O1, H1, L1, C1, tsc[ii], ev["side"][ii].astype(np.int64), ev["lv"][ii], ev["atr"][ii], bs, p["ch"],
                                                DE.ALIVE, DE.HOLD, S["take_atr"], S["stop_atr"], S["hard_stop_atr"], DE.FEE_IN, DE.FEE_TAKE, DE.FEE_OUT, DE.FUND)
    for key, v in (("coin", np.full(len(ii), c)), ("t", tsc[ii]), ("side", ev["side"][ii]), ("lv", ev["lv"][ii]), ("atr", ev["atr"][ii]), ("score", cur[ii]),
                   ("thr", th[ii]), ("filled", fl), ("t1h", t1h), ("fill", fill), ("R", R), ("kind", kind), ("tout", tout), ("grp", np.full(len(ii), GROUP.get(c, "new")))):
        out[key].append(v)
O = {k: np.concatenate(v) for k, v in out.items()}
np.savez_compressed(f"{ST}/wf/allorders_{stream}_rs{VAR}.npz", **O)
fr = O["filled"].astype(bool)
print(f"{VAR}: ордеров {len(O['t'])}, исполнено {fr.sum()}, R исполненных {np.nanmean(O['R'][fr]):+.3f}; пороги {[round(x, 3) for x in THR[-4:]]}", flush=True)
print("allorders rs done", VAR, flush=True)
