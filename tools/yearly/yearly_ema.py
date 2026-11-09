"""The yearly fallback — 📐 EMA: the deployed recipe (ema_repro.py / er_export2.py EXPORT: 3 LightGBM seeds 0..2 on every touch
older than the last one - hold - 1 day, the label F_0.75_4.0_3 clipped to [-1.5, 5]; the threshold = q 0.96 of the scores of the
last 365 days) on the touches rebuilt from the data to the year's end (dl.py -> er_build -> er_df -> er_lab3 -> er_pen). Run in
tools/ema_model. Checks: (A) the deployed model reproduced at its own end (the scores' correlation on a 60k sample >= 0.95 — the
recipe: 0.987; the threshold within 15%); (B) newer data: the new last touch >= MIN_DAYS (60) after the deployed one; (D) not broken —
finite, correlation with the old on the last 90 days >= 0.2, the top 1% above the average label, the threshold within x0.5 .. x2.
-> <out>/vp_ema_model.json (the deployed file, new trees / thr / trained_to; the rule, filters, research unchanged), <out>/ema_report.json
usage: YEAR=2027 OUT=dir python3 ../yearly/yearly_ema.py"""
import os, sys, json, time, numpy as np, pandas as pd, lightgbm as lgb, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.getcwd()); sys.path.append(os.path.join(os.getcwd(), "..", "winrate"))   # treevec
from common import D
from lgbpure import export, predict
import treevec as TV
YEAR = int(os.environ["YEAR"]); OUT = os.environ.get("OUT", "yearly_out"); os.makedirs(OUT, exist_ok=True)
ROOT = os.path.join(os.getcwd(), "..", ".."); M0 = json.load(open(os.path.join(ROOT, "vp_ema_model.json")))
rep = {"model": "ema", "year": YEAR, "ok": False, "checks": {}}
def done(ok, why):
    rep["ok"] = ok; rep["why"] = why
    json.dump(rep, open(os.path.join(OUT, "ema_report.json"), "w"), indent=1, default=float)
    print(("ПРИНЯТО: " if ok else "НЕ ПРИНЯТО: ") + why, flush=True); sys.exit(0 if ok else 3)
LAB, F = M0["lab"], M0["feats"]; TAKE, HOLD = 4.0, 3.0; Q = float(M0.get("q", 0.96))
d = pd.read_parquet(f"{D}/er_all.parquet", columns=["sym", "t", "side", "tf_s"] + [c for c in F if c != "side"] + [LAB])
T = d.t.values; X = d[F].values.astype(np.float64); y = np.nan_to_num(d[LAB].values, nan=0.0).clip(-1.5, TAKE + 1)
def fit(end):
    tr = T < end - HOLD * 86400 - 86400; trees, ms = [], []
    for s in range(3):
        m = lgb.LGBMRegressor(n_estimators=500, learning_rate=0.02, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1,
                              colsample_bytree=0.6, reg_lambda=5.0, verbose=-1, n_jobs=4, random_state=s).fit(X[tr], y[tr])
        trees.append(export(m.booster_, F)["trees"]); ms.append(m)
    return trees, (lambda Xs: sum(m.predict(Xs) for m in ms) / 3), int(tr.sum())
def thr_at(end, f):
    last = (T >= end - 365 * 86400) & (T <= end)
    return float(np.quantile(f(X[last]), Q))
# (A) the deployed one reproduced at its own end
end0 = int(M0["trained_to"]); _, f0, _ = fit(end0)
rng = np.random.default_rng(1); smp = rng.choice(np.flatnonzero(T <= end0), min(60000, int((T <= end0).sum())), replace=False)
dep = TV.model_score(M0["models"], X[smp]); new = f0(X[smp]); cor = float(np.corrcoef(dep, new)[0, 1])
thr0 = float(M0["thr"]); thr0r = thr_at(end0, f0)
rep["checks"]["A"] = {"corr": round(cor, 4), "thr_deployed": thr0, "thr_rebuilt": thr0r, "need": {"corr": 0.95, "thr": 0.15}}
print(f"(A) воспроизведение на старом конце: корреляция {cor:.4f}; порог бота {thr0:.4f}, пересобранный {thr0r:.4f}", flush=True)
if cor < 0.95 or abs(thr0r - thr0) > 0.15 * abs(thr0):
    done(False, f"нынешняя модель не воспроизвелась (корреляция {cor:.3f}, порог {thr0r:.4f} против {thr0:.4f})")
# (B) newer data (EMA's model is the latest of the yearly ones: September 2026; the year's end adds ~3 months)
end1 = int(T.max())   # always the data's end (a rehearsal's CUT_AT is for the models cut a year back; EMA's ends in September)
rep["checks"]["B"] = {"end": end1, "old_end": end0}
print(f"(B) последнее касание {time.strftime('%Y-%m-%d', time.gmtime(end1))}, было {time.strftime('%Y-%m-%d', time.gmtime(end0))}", flush=True)
if end1 - end0 < int(os.environ.get("MIN_DAYS_EMA", "60")) * 86400:
    done(False, "нет новых данных (меньше 60 дней после нынешней модели)")
trees, f1, n1 = fit(end1); thr1 = thr_at(end1, f1)
# (D) not broken
w = np.flatnonzero((T >= end1 - 90 * 86400) & (T <= end1))
o_ = TV.model_score(M0["models"], X[w]); n_ = f1(X[w])
cor2 = float(np.corrcoef(o_, n_)[0, 1]) if np.std(n_) > 0 else 0.0
ly = np.flatnonzero((T >= end1 - 365 * 86400) & (T <= end1 - HOLD * 86400 - 86400)); sl = f1(X[ly]); top = sl > np.quantile(sl, 0.99)
lift = float(np.mean(y[ly][top]) - np.mean(y[ly])); fin = bool(np.all(np.isfinite(n_)) and np.std(n_) > 0); rt = thr1 / thr0 if thr0 else 0.0
rep["checks"]["D"] = {"corr_old_new": round(cor2, 4), "top1_lift": round(lift, 4), "finite": fin, "thr_new": thr1, "thr_ratio": round(rt, 3)}
print(f"(D) конечные {fin}; корреляция старой и новой на 90 днях {cor2:.3f}; верхний 1% лучше среднего на {lift:+.3f}; порог {thr0:.4f} -> {thr1:.4f} (×{rt:.2f})", flush=True)
if not (fin and cor2 >= 0.2 and lift > 0 and 0.5 <= rt <= 2.0):
    done(False, f"новая модель похожа на сломанную (конечные {fin}, корреляция {cor2:.2f}, выигрыш {lift:+.3f}, порог ×{rt:.2f})")
M = dict(M0, models=trees, thr=round(thr1, 6), trained_to=end1, retrained={"by": "yearly fallback (GitHub Actions)", "t": int(time.time()), "events": n1})
json.dump(M, open(os.path.join(OUT, "vp_ema_model.json"), "w"), separators=(",", ":"))
rep["trained_to"] = end1
done(True, f"переобучена по {time.strftime('%d.%m.%Y', time.gmtime(end1))} ({n1} касаний), порог {thr0:.4f} → {thr1:.4f}, правило прежнее")
