"""The yearly fallback — ⚡ the 4h streams (wick4h, the shifted wick4h_o2): the deployed recipe (dlm_lab_export.py LABEL=feat — it IS
the deployed model, RETRAIN.md): LightGBM on the bot's own order features of the train coins' filled orders (the 127's 2 of 3), 10
seeds x the 28 / 33 features, the stored label R clipped +-1.5, on everything closed 3 days before the data's end; the threshold =
q 0.99 of the last 12 months' orders scored by the ensemble trained before them (out of sample); the shifted stream's x1.05 (v0.99.766);
the fallback keeps the deployed threshold's quantile level (wick4h's sits a little under 0.99).
The 2h stream (close2h: its own restored engine) stays — the main way retrains it. Run in tools/winrate after dlm_build.py on the data
to the year's end (LABSTORE/feat/<stream>). Checks per stream: (A) the deployed ensemble reproduced at its own end (the scores'
correlation on 600 orders >= 0.95), its threshold's level among the out-of-sample scores within 0.95 .. 0.999; (B) newer data (>= MIN_DAYS_DLM, 60, after it); (D) not broken —
finite, correlation with the old on the last 90 days >= 0.2, the top 1% above the average label, the threshold within x0.5 .. x2.
Both streams must pass, else nothing is written. -> <out>/vp_dlm_model.json, <out>/dlm_report.json
usage: YEAR=2027 OUT=dir python3 ../yearly/yearly_dlm.py"""
import os, sys, json, time, numpy as np, lightgbm as lgb, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.getcwd())
import dlm_engine as DE, treevec as TV
from common import V
from rbs_export import export
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store"); NS = int(os.environ.get("NS", "10"))
YEAR = int(os.environ["YEAR"]); OUT = os.environ.get("OUT", "yearly_out"); os.makedirs(OUT, exist_ok=True)
ROOT = os.path.join(os.getcwd(), "..", ".."); MJ = json.load(open(os.path.join(ROOT, "vp_dlm_model.json")))
rep = {"model": "dlm", "year": YEAR, "ok": False, "checks": {}}
def done(ok, why):
    rep["ok"] = ok; rep["why"] = why
    json.dump(rep, open(os.path.join(OUT, "dlm_report.json"), "w"), indent=1, default=float)
    print(("ПРИНЯТО: " if ok else "НЕ ПРИНЯТО: ") + why, flush=True); sys.exit(0 if ok else 3)
C = json.load(open(f"{ST}/feat_coins.json"))
def bn(gs):
    b = gs.replace("_USDT", "")
    for c in (b + "USDT", "1000" + b + "USDT"):
        if c in C["base"] or c in C["new"]: return c
r127 = sorted({bn(c) for c in V.RESEARCH_COINS_127 if bn(c)}); check = set(r127[2::3]); train = sorted(set(r127) - check)
pr = dict(n_estimators=300, learning_rate=0.05, num_leaves=63, min_child_samples=1000, subsample=0.7, subsample_freq=1, colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
MULT = {"wick4h": 1.0, "wick4h_o2": 1.05}
out = json.loads(json.dumps(MJ)); t0 = time.time()
for S in out["streams"]:
    st = S["name"]
    if st not in MULT: continue
    rows = {k: [] for k in ("t", "F", "R", "tout")}
    for c in train:
        fn = f"{ST}/feat/{st}/{c}.npz"
        if not os.path.exists(fn): continue
        z = np.load(fn)
        if not len(z["t"]): continue
        k = np.isfinite(z["R"])
        rows["t"].append(z["t"][k]); rows["F"].append(z["F"][k]); rows["R"].append(z["R"][k]); rows["tout"].append(z["tout"][k])
    D = {k: np.concatenate(v) for k, v in rows.items()}; y = np.clip(D["R"], -1.5, 1.5)
    def ens(m):
        return [(X_, lgb.LGBMRegressor(random_state=sd, **pr).fit(D["F"][m][:, :X_], y[m])) for X_ in (28, 33) for sd in range(NS)]
    def score(E, idx):
        return np.mean([m.predict(D["F"][idx][:, :X_]) for X_, m in E], axis=0)
    def oos(end):   # the last 12 months' orders scored by the ensemble trained before them (out of sample)
        cut = end - 365 * 86400; old = ens(D["tout"] < cut - 3 * 86400); ref = np.flatnonzero((D["t"] >= cut) & (D["tout"] <= end))
        return score(old, ref)
    # (A) the deployed ensemble reproduced at its own end
    end0 = int(S.get("trained_to") or MJ["trained_to"]) + 3 * 86400
    m0 = D["tout"] <= end0; E0 = ens(D["tout"] < end0 - 3 * 86400)
    smp = np.flatnonzero(m0 & (D["t"] >= end0 - 365 * 86400)); smp = smp[::max(1, len(smp) // 600)][:600]
    a = score(E0, smp); b = TV.model_score(S["models"], D["F"][smp].astype(float)); cor = float(np.corrcoef(a, b)[0, 1])
    # the deployed threshold's own level among the out-of-sample scores (the recipe says q 0.99; wick4h's 0.4437 of v0.99.759 sits a
    # little lower — the trees reproduce exactly, its source is not in the notes): the new model's threshold at the same level, so
    # the fallback never changes how often ⚡ trades on its own
    s0 = oos(end0); t0d = float(S["thr"]); qe = float(np.mean(s0 < t0d / MULT[st])); t0r = float(np.quantile(s0, 0.99)) * MULT[st]
    print(f"(A) {st}: воспроизведение на старом конце {time.strftime('%Y-%m-%d', time.gmtime(end0))}: корреляция {cor:.4f} ({len(smp)} заявок); порог бота {t0d:.4f} = квантиль {qe:.4f} честных оценок (рецепт q 0.99 дал бы {t0r:.4f}); {time.time() - t0:.0f}s", flush=True)
    rep["checks"].setdefault("A", {})[st] = {"corr": round(cor, 4), "thr_deployed": t0d, "q_level": round(qe, 4), "thr_q99": t0r}
    if cor < 0.95 or not 0.95 <= qe <= 0.999:
        done(False, f"{st}: нынешняя модель не воспроизвелась (корреляция {cor:.3f}, порог бота на квантиле {qe:.4f})")
    # (B) newer data
    end1 = int(D["tout"].max())   # always the data's end (a rehearsal's CUT_AT is for the models cut a year back; ⚡'s end in September)
    rep["checks"].setdefault("B", {})[st] = {"end": end1, "old_end": end0}
    if end1 - end0 < int(os.environ.get("MIN_DAYS_DLM", "60")) * 86400:
        done(False, f"{st}: нет новых данных (меньше 60 дней после нынешней модели)")
    E1 = ens(D["tout"] < end1 - 3 * 86400); t1 = float(np.quantile(oos(end1), qe)) * MULT[st]
    models = [export(m.booster_, [f"f{i}" for i in range(X_)])["trees"] for X_, m in E1]
    # (D) not broken
    w = np.flatnonzero((D["t"] >= end1 - 90 * 86400) & (D["tout"] <= end1))
    o_ = TV.model_score(S["models"], D["F"][w].astype(float)); n_ = score(E1, w)
    cor2 = float(np.corrcoef(o_, n_)[0, 1]) if np.std(n_) > 0 else 0.0
    ly = np.flatnonzero((D["t"] >= end1 - 365 * 86400) & (D["tout"] < end1 - 3 * 86400)); sl = score(E1, ly); top = sl > np.quantile(sl, 0.99)
    lift = float(np.mean(y[ly][top]) - np.mean(y[ly])); fin = bool(np.all(np.isfinite(n_)) and np.std(n_) > 0); rt = t1 / t0d if t0d else 0.0
    print(f"(D) {st}: конечные {fin}; корреляция старой и новой на 90 днях {cor2:.3f}; верхний 1% лучше среднего на {lift:+.3f}; порог {t0d:.4f} -> {t1:.4f} (×{rt:.2f}); {time.time() - t0:.0f}s", flush=True)
    rep["checks"].setdefault("D", {})[st] = {"corr_old_new": round(cor2, 4), "top1_lift": round(lift, 4), "finite": fin, "thr_new": t1, "thr_ratio": round(rt, 3)}
    if not (fin and cor2 >= 0.2 and lift > 0 and 0.5 <= rt <= 2.0):
        done(False, f"{st}: новая модель похожа на сломанную (конечные {fin}, корреляция {cor2:.2f}, выигрыш {lift:+.3f}, порог ×{rt:.2f})")
    S["models"] = models; S["trained_to"] = int(end1 - 3 * 86400)
    if "thr_base" in S:   # the shifted stream: the export's threshold and the bot's x1.05 (t_dlm_o2 checks thr == thr_base x 1.05)
        S["thr_base"] = round(t1 / MULT[st], 6); S["thr"] = round(S["thr_base"] * MULT[st], 6)
    else:
        S["thr"] = round(t1, 6)
out["retrained"] = {"by": "yearly fallback (GitHub Actions)", "t": int(time.time()), "streams": list(MULT)}
json.dump(out, open(os.path.join(OUT, "vp_dlm_model.json"), "w"), separators=(",", ":"))
done(True, "потоки 4ч и 4ч со сдвигом переобучены по " + time.strftime("%d.%m.%Y", time.gmtime(end1 - 3 * 86400))
     + "; поток 2ч прежний; пороги " + ", ".join(f"{s} {rep['checks']['A'][s]['thr_deployed']:.3f} → {rep['checks']['D'][s]['thr_new']:.3f}" for s in MULT))
