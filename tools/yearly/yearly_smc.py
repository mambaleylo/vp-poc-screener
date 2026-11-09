"""The yearly fallback — 🧱 SMC: the deployed recipe (new_ind/smc_export.py, lv_wf.scores: the bot coins' SMC touches lv2 fam >= 33,
the label E2 clipped to [-1.2, 6], 2 LightGBM seeds 0 / 1 on everything closed 14 days before the cut) with the cut as a parameter;
the threshold the walk-forward way (lv_wf.scores' THR, smc_export5.py): the quantile q of the year before's OUT-OF-SAMPLE scores
(the model cut 14 days before that year). Run in tools/winrate with LVDIR = the events on the data to the year's end. Checks:
  (A) the deployed model reproduced at ITS cut: the scores' correlation on the year after >= 0.90 (the recipe: 0.976, HANDOFF);
      its threshold the same way within 15% (information when the year before has too few events);
  (B) a new year: the new cut >= 300 days after the deployed one, the data reach it;
  (D) a broken model, not a changed one: the scores finite, the correlation with the old on the 90 days before the cut >= 0.2,
      the top 1% of its last training year above the year's average label, the new threshold within x0.5 .. x2 of the old.
Written: <out>/vp_smc_model.json — the deployed file with the new trees, thr, trained_to, thr_from (the rule, the research and the
backtest list unchanged) — and <out>/smc_report.json. usage: YEAR=2027 OUT=dir LVDIR=dir python3 ../yearly/yearly_smc.py"""
import os, sys, json, time, numpy as np, lightgbm as lgb, warnings
warnings.filterwarnings("ignore")
HERE = os.getcwd(); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "new_ind")); sys.path += [os.path.join(HERE, "..", "zones_model"), os.path.join(HERE, "..", "neuro_model")]
import types; sys.modules.setdefault("nx_h", types.SimpleNamespace(pain=None))
from lv_wf import load_dir, ts
import lv_engine as LE, treevec as TV
from lgbpure import export
YEAR = int(os.environ["YEAR"]); OUT = os.environ.get("OUT", "yearly_out"); os.makedirs(OUT, exist_ok=True)
ROOT = os.path.join(HERE, "..", ".."); M0 = json.load(open(os.path.join(ROOT, "vp_smc_model.json")))
rep = {"model": "smc", "year": YEAR, "ok": False, "checks": {}}
def done(ok, why):
    rep["ok"] = ok; rep["why"] = why
    json.dump(rep, open(os.path.join(OUT, "smc_report.json"), "w"), indent=1, default=float)
    print(("ПРИНЯТО: " if ok else "НЕ ПРИНЯТО: ") + why, flush=True); sys.exit(0 if ok else 3)
Dd = load_dir(os.environ.get("LVDIR", "lv2"), LE.FNAMES)
F = Dd["F"]; T = Dd["T"]; BOT = Dd["BOT"]; S = F[:, 0].astype(int) >= 33
y = np.nan_to_num(Dd["R"][2], nan=0.0).clip(-1.2, 6.0)
pr = dict(n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=300, subsample=0.7, subsample_freq=1, colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
Q = float(M0.get("q", 0.993)); mods0 = M0["models"] if isinstance(M0["models"], list) else list(M0["models"].values())
def fit(cut):
    tr = S & BOT & (T < cut); trees, ms = [], []
    for s in range(2):
        m = lgb.LGBMRegressor(random_state=s, **pr).fit(F[tr], y[tr]); trees.append(export(m.booster_, LE.FNAMES)["trees"]); ms.append(m)
    return trees, (lambda X: sum(m.predict(X) for m in ms) / 2), int(tr.sum())
def thr_for(cut_new, f_prev):
    """the walk-forward threshold of the model cut at cut_new: q of the previous model's out-of-sample scores on the year before"""
    yb = time.gmtime(cut_new + 14 * 86400).tm_year
    ref = np.flatnonzero(S & BOT & (T >= ts(yb - 1)) & (T < cut_new))
    return (float(np.quantile(f_prev(F[ref]), Q)) if len(ref) >= 200 else None), int(len(ref))
# (A) the deployed one reproduced at its own cut
cut0 = int(M0["trained_to"]); te = np.flatnonzero(S & BOT & (T >= cut0 + 14 * 86400) & (T < cut0 + 14 * 86400 + 365 * 86400))
_, f0, n0 = fit(cut0)
a = f0(F[te]); b = TV.model_score(mods0, F[te].astype(float)); cor = float(np.corrcoef(a, b)[0, 1])
thr0 = float(M0["thr"] if not isinstance(M0["thr"], dict) else list(M0["thr"].values())[0])
y0 = time.gmtime(cut0 + 14 * 86400).tm_year
_, fpp, _ = fit(ts(y0 - 1) - 14 * 86400); thr0r, nref0 = thr_for(cut0, fpp)
rep["checks"]["A"] = {"corr": round(cor, 4), "events": int(len(te)), "thr_deployed": thr0, "thr_rebuilt": thr0r, "need": {"corr": 0.90, "thr": 0.15}}
print(f"(A) воспроизведение на старом срезе: корреляция {cor:.4f} ({len(te)} касаний); порог бота {thr0:.4f}, пересобранный {thr0r if thr0r is None else round(thr0r, 4)} ({nref0} событий)", flush=True)
if cor < 0.90 or (thr0r is not None and abs(thr0r - thr0) > 0.15 * abs(thr0)):
    done(False, f"нынешняя модель не воспроизвелась (корреляция {cor:.3f}, порог {thr0r} против {thr0:.4f}) — переобучать рецептом нельзя")
# (B) a new year
CUT = ts(YEAR) - 14 * 86400; last = int(T.max())
if os.environ.get("CUT_AT"):   # a rehearsal only (the data end before the year)
    CUT = int(time.mktime(time.strptime(os.environ["CUT_AT"], "%Y-%m-%d")) - time.timezone)
rep["checks"]["B"] = {"cut": CUT, "old_cut": cut0, "last_event": last}
print(f"(B) срез {time.strftime('%Y-%m-%d', time.gmtime(CUT))}, был {time.strftime('%Y-%m-%d', time.gmtime(cut0))}, последнее событие {time.strftime('%Y-%m-%d', time.gmtime(last))}", flush=True)
if CUT - cut0 < int(os.environ.get("MIN_DAYS", "300")) * 86400 or last < CUT:
    done(False, "нет нового года данных")
trees, f1, n1 = fit(CUT)
thr1, nref1 = thr_for(CUT, f0) if not os.environ.get("CUT_AT") else (float(np.quantile(f0(F[np.flatnonzero(S & BOT & (T >= cut0 + 14 * 86400) & (T < CUT))]), Q)), -1)
# (D) a broken model, not a changed one
w = np.flatnonzero(S & BOT & (T >= CUT - 90 * 86400) & (T < CUT))
o_ = TV.model_score(mods0, F[w].astype(float)); n_ = f1(F[w])
cor2 = float(np.corrcoef(o_, n_)[0, 1]) if np.std(n_) > 0 else 0.0
ly = np.flatnonzero(S & BOT & (T >= CUT - 365 * 86400) & (T < CUT)); sl = f1(F[ly]); top = sl > np.quantile(sl, 0.99)
lift = float(np.mean(y[ly][top]) - np.mean(y[ly])); fin = bool(np.all(np.isfinite(n_)) and np.std(n_) > 0)
rt = (thr1 / thr0) if (thr1 and thr0) else 0.0
rep["checks"]["D"] = {"corr_old_new": round(cor2, 4), "top1_lift": round(lift, 4), "finite": fin, "thr_new": thr1, "thr_ratio": round(rt, 3)}
print(f"(D) оценки конечные: {fin}; корреляция старой и новой на 90 днях {cor2:.3f}; верхний 1% лучше среднего на {lift:+.3f}; порог {thr0:.4f} -> {thr1:.4f} (×{rt:.2f})", flush=True)
if not (fin and cor2 >= 0.2 and lift > 0 and 0.5 <= rt <= 2.0):
    done(False, f"новая модель похожа на сломанную (конечные {fin}, корреляция {cor2:.2f}, выигрыш {lift:+.3f}, порог ×{rt:.2f})")
M = dict(M0, models=trees, thr=round(thr1, 6), trained_to=int(CUT),
         thr_from=f"{time.gmtime(CUT + 14 * 86400).tm_year - 1} out of sample (the walk-forward rule), q {Q:g} — the yearly fallback",
         retrained={"by": "yearly fallback (GitHub Actions)", "t": int(time.time()), "events": n1})
json.dump(M, open(os.path.join(OUT, "vp_smc_model.json"), "w"), separators=(",", ":"))
rep["trained_to"] = int(CUT); rep["train_events"] = n1
done(True, f"переобучена по {time.strftime('%d.%m.%Y', time.gmtime(CUT))} ({n1} касаний), порог {thr0:.4f} → {thr1:.4f}, правило прежнее")
