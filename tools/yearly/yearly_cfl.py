"""The yearly fallback — 🔄 Классика (tools/yearly, the user: "запасной вариант"): the deployed recipe (cfl_export.py: 2 LightGBM,
seeds 0 / 1, on the bot coins' ev3 events from 2021 to the cut, the flipped label of fc_red.py) with the cut as a parameter.
Run in tools/winrate after ev3_engine.py and fc_red.py on the data to the year's end. Checks (all must hold, else nothing is
written and the reason is reported):
  (A) the deployed model reproduced at ITS cut: the scores' correlation on the year after it >= 0.93, the top 0.3% picks shared
      >= 65% (the recipe's own level: 0.95 / 76%, HANDOFF);
  (B) new data: the new cut at least 300 days after the deployed one;
  (D) sanity (a broken model, not a changed one — see the step): the scores finite, the correlation with the old >= 0.2 (the
      past yearly retrains: 0.37–0.43), the new model's top 1% above its last training year's average label.
Written: <out>/vp_cfl_model.json — the deployed file with the new trees, the threshold seed (the bot coins' days, the 194 before
the year's start), trained_to / seed_to; the rule, the filters, the research and the backtest list unchanged (the rule was chosen
on the walk-forward of earlier years — the yearly retrain only refreshes the model) — and <out>/cfl_report.json.
usage: YEAR=2027 OUT=dir python3 ../yearly/yearly_cfl.py"""
import os, sys, json, math, time, numpy as np, lightgbm as lgb, warnings
warnings.filterwarnings("ignore")
HERE = os.getcwd(); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "new_ind")); sys.path += [os.path.join(HERE, "..", "zones_model"), os.path.join(HERE, "..", "neuro_model")]
import types; sys.modules.setdefault("nx_h", types.SimpleNamespace(pain=None))
sys.argv = ["x"]
from lv_wf import load_dir, ts
import ev3_engine as E3, ev2_engine as E2, treevec as TV
from lgbpure import export
YEAR = int(os.environ["YEAR"]); OUT = os.environ.get("OUT", "yearly_out"); os.makedirs(OUT, exist_ok=True)
ROOT = os.path.join(HERE, "..", ".."); M0 = json.load(open(os.path.join(ROOT, "vp_cfl_model.json")))
rep = {"model": "cfl", "year": YEAR, "ok": False, "checks": {}}
def done(ok, why):
    rep["ok"] = ok; rep["why"] = why
    json.dump(rep, open(os.path.join(OUT, "cfl_report.json"), "w"), indent=1, default=float)
    print(("ПРИНЯТО: " if ok else "НЕ ПРИНЯТО: ") + why, flush=True); sys.exit(0 if ok else 3)
Dd = load_dir("ev3", E3.FNAMES); T, SIDE, BOT, F = Dd["T"], Dd["SIDE"], Dd["BOT"], Dd["F"]
F[:, [E2.FNAMES.index(c) for c in M0["zero"]]] = 0.0
RF = np.load("fc_RF.npz")["RF"]; y = np.nan_to_num(RF, nan=0.0).clip(-1.2, 6.0)
MASK = T >= ts(2021)
pr = dict(n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=300, subsample=0.7, subsample_freq=1, colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
def fit(cut):
    tr = MASK & BOT & (T < cut); trees, ms = [], []
    for s in range(2):
        m = lgb.LGBMRegressor(random_state=s, **pr).fit(F[tr], y[tr]); trees.append(export(m.booster_, E2.FNAMES)["trees"]); ms.append(m)
    return trees, (lambda X: sum(m.predict(X) for m in ms) / 2), int(tr.sum())
# (A) the deployed one reproduced at its own cut
cut0 = int(M0["trained_to"]); te = np.flatnonzero(MASK & BOT & (T >= cut0 + 14 * 86400) & (T < cut0 + 14 * 86400 + 365 * 86400))
_, f0, n0 = fit(cut0)
a = f0(F[te]); b = TV.model_score(M0["models"], F[te].astype(float))
cor = float(np.corrcoef(a, b)[0, 1]); A_, B_ = a > np.quantile(a, 0.997), b > np.quantile(b, 0.997); share = float((A_ & B_).sum() / max(1, B_.sum()))
rep["checks"]["A"] = {"corr": round(cor, 4), "top03_shared": round(share, 3), "events": int(len(te)), "need": [0.93, 0.65]}
print(f"(A) воспроизведение на старом срезе: корреляция {cor:.4f}, общих в верхних 0.3% {share * 100:.0f}% ({len(te)} событий)", flush=True)
if not (cor >= 0.93 and share >= 0.65):
    done(False, f"нынешняя модель не воспроизвелась (корреляция {cor:.3f}, общих {share * 100:.0f}%) — переобучать рецептом нельзя")
# (B) new data
CUT = ts(YEAR) - 14 * 86400; last = int(T.max())
if os.environ.get("CUT_AT"):   # a rehearsal only (the data ends before the year): the cut given, the minimum gap MIN_DAYS
    CUT = int(time.mktime(time.strptime(os.environ["CUT_AT"], "%Y-%m-%d")) - time.timezone)
rep["checks"]["B"] = {"cut": CUT, "old_cut": cut0, "last_event": last}
print(f"(B) срез {time.strftime('%Y-%m-%d', time.gmtime(CUT))}, был {time.strftime('%Y-%m-%d', time.gmtime(cut0))}, последнее событие {time.strftime('%Y-%m-%d', time.gmtime(last))}", flush=True)
if CUT - cut0 < int(os.environ.get("MIN_DAYS", "300")) * 86400 or last < CUT:
    done(False, "нет нового года данных (срез не дальше старого на 300 дней или данных до среза нет)")
trees, f1, n1 = fit(CUT)
# (D) sanity — a broken model, not a changed one: the yearly retrains of this recipe moved the scores a lot (old vs new on the 90
# days before the new cut: correlation 0.37 / 0.43 / 0.41 for 2023 / 2024 / 2025 — the new one has seen those days), and the
# picks follow each model's own rolling quantile, so their number holds by construction. Checked: the scores finite and not
# flat, the correlation with the old >= 0.2, and the new model's top 1% in its last training year above the year's average label
w = np.flatnonzero(MASK & BOT & (T >= CUT - 90 * 86400) & (T < CUT))
o_ = TV.model_score(M0["models"], F[w].astype(float)); n_ = f1(F[w])
cor2 = float(np.corrcoef(o_, n_)[0, 1]) if np.std(n_) > 0 else 0.0
ly = np.flatnonzero(MASK & BOT & (T >= CUT - 365 * 86400) & (T < CUT)); sl = f1(F[ly]); top = sl > np.quantile(sl, 0.99)
lift = float(np.mean(y[ly][top]) - np.mean(y[ly])); fin = bool(np.all(np.isfinite(n_)) and np.std(n_) > 0)
rep["checks"]["D"] = {"corr_old_new": round(cor2, 4), "top1_lift": round(lift, 4), "finite": fin, "need": {"corr": 0.2, "lift": 0.0}}
print(f"(D) оценки конечные: {fin}; корреляция старой и новой на 90 днях {cor2:.3f} (история 0.37–0.43); верхний 1% новой лучше среднего на {lift:+.3f}", flush=True)
if not (fin and cor2 >= 0.2 and lift > 0):
    done(False, f"новая модель похожа на сломанную (конечные {fin}, корреляция {cor2:.2f}, выигрыш верхнего 1% {lift:+.3f})")
# the threshold seed: the bot coins' events of the 194 days before the year's start, per UTC day: n and the 300 best
NOW = CUT + 14 * 86400; m_ = BOT & MASK & (T >= NOW - 194 * 86400) & (T < NOW); sc = np.zeros(len(T)); sc[m_] = f1(F[m_])
seed = {}
for d in np.unique(T[m_] // 86400):
    v = np.sort(sc[m_ & (T // 86400 == d)])[::-1]; seed[str(int(d))] = [int(len(v)), [round(float(x), 5) for x in v[:300]]]
M = dict(M0, models=trees, trained_to=int(CUT), seed=seed, seed_to=int(NOW), retrained={"by": "yearly fallback (GitHub Actions)", "t": int(time.time()), "events": n1})
json.dump(M, open(os.path.join(OUT, "vp_cfl_model.json"), "w"), separators=(",", ":"))
rep["trained_to"] = int(CUT); rep["train_events"] = n1
done(True, f"переобучена по {time.strftime('%d.%m.%Y', time.gmtime(CUT))} ({n1} событий), правило и фильтры прежние")
