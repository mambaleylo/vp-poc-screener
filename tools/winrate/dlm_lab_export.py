"""⚡ candidate model (the lab's recipe that won the strictest money: dlm_allorders.py's — LightGBM on the BOT's own order
features of the train coins' filled orders, 10 seeds x the 28 / 33 features, the label R clipped +-1.5), now relabelled with
the bot's CURRENT exits (each stream's take / close stop / emergency stop of vp_dlm_model.json) and trained on everything
closed 3 days before the data's end. The threshold (q 0.99, as the walk-forward): the scores of the train coins' filled orders
of the last 12 months by an ensemble trained before them (out of sample). -> <LABSTORE>/wf/vp_dlm_model_lab.json (the bot's
format; the deployed file untouched)"""
import os, sys, json, time, numpy as np, lightgbm as lgb, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlm_engine as DE, treevec as TV
from common import V
from rbs_export import export
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store"); NS = int(os.environ.get("NS", "10"))
MJ = json.load(open("/home/user/vp-poc-screener/vp_dlm_model.json"))
C = json.load(open(f"{ST}/feat_coins.json"))
def bn(gs):
    b = gs.replace("_USDT", "")
    for c in (b + "USDT", "1000" + b + "USDT"):
        if c in C["base"] or c in C["new"]: return c
r127 = sorted({bn(c) for c in V.RESEARCH_COINS_127 if bn(c)}); check = set(r127[2::3]); train = sorted(set(r127) - check)
pr = dict(n_estimators=300, learning_rate=0.05, num_leaves=63, min_child_samples=1000, subsample=0.7, subsample_freq=1, colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
out = json.loads(json.dumps(MJ)); t0 = time.time(); tmax_all = 0
for S in out["streams"]:
    st = S["name"]; p = DE.STREAMS[st]; bs = p["hh"] * 3600; rows = {k: [] for k in ("t", "F", "R", "tout")}
    for c in train:
        z = np.load(f"{ST}/feat/{st}/{c}.npz")
        if not len(z["t"]): continue
        T1, O1, H1, L1, C1, V1 = DE.load1h(c)
        fl, _, _, R, _, to = DE.fill_walk(T1, O1, H1, L1, C1, z["t"].astype(np.int64), z["side"].astype(np.int64), z["lv"], z["atr"], bs, p["ch"],
                                          DE.ALIVE, DE.HOLD, S["take_atr"], S["stop_atr"], S["hard_stop_atr"], DE.FEE_IN, DE.FEE_TAKE, DE.FEE_OUT, DE.FUND)
        k = fl & np.isfinite(R)
        rows["t"].append(z["t"][k]); rows["F"].append(z["F"][k]); rows["R"].append(R[k]); rows["tout"].append(to[k])
    D = {k: np.concatenate(v) for k, v in rows.items()}; y = np.clip(D["R"], -1.5, 1.5); end = int(D["tout"].max()); tmax_all = max(tmax_all, end)
    def ens(m):
        return [(X_, lgb.LGBMRegressor(random_state=sd, **pr).fit(D["F"][m][:, :X_], y[m])) for X_ in (28, 33) for sd in range(NS)]
    cut = end - 365 * 86400
    old = ens(D["tout"] < cut - 3 * 86400); ref = D["t"] >= cut
    sc_ref = np.mean([m.predict(D["F"][ref][:, :X_]) for X_, m in old], axis=0); thr = float(np.quantile(sc_ref, 0.99))
    new = ens(D["tout"] < end - 3 * 86400)
    models = [export(m.booster_, [f"f{i}" for i in range(X_)])["trees"] for X_, m in new]
    smp = np.flatnonzero(ref)[::max(1, ref.sum() // 300)][:300]
    d = np.max(np.abs(TV.model_score(models, D["F"][smp].astype(float)) - np.mean([m.predict(D["F"][smp][:, :X_]) for X_, m in new], axis=0)))
    assert d < 1e-6, d
    S["models"] = models; S["thr"] = round(thr, 6)
    print(f"{st}: обучено на {len(new and D['t'][D['tout'] < end - 3 * 86400])} сделках, R метки {D['R'].mean():+.3f}, порог {thr:.4f} (у бота {[s for s in MJ['streams'] if s['name'] == st][0]['thr']}), сверка деревьев {d:.1e}, {time.time() - t0:.0f}s", flush=True)
out["trained_to"] = int(tmax_all - 3 * 86400); out["made"] = int(time.time())
out["research"]["lab_export"] = {"recipe": "bot-feature orders, current exits, train coins, 10 seeds x 28/33", "why": "money_4h.py: lab models > the research-engine ones"}
json.dump(out, open(f"{ST}/wf/vp_dlm_model_lab.json", "w"), separators=(",", ":"))
print("lab export done", flush=True)
