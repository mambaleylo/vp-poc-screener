"""The yearly fallback — ⚡ the 2h stream (close2h): the deployed recipe (s21h2_repro.py / s26_mix.py: the restored engine's d2 events
on the 2020- candles, the exit E1 clipped +-1.5, 10 seeds on the 28 features + 10 on the 28 + 5 daily ones, the train coins — every 3rd
from the 3rd is a check coin — with events before the cut, the cut 3 days before the year) with the cut as a parameter. The threshold
keeps the deployed one's level: its quantile among the deployed scores of the train coins' 365 days before the cut, taken of the new
model's scores there (s21h2_refresh.py's rule). Run in tools/winrate after s21h2_engine.py and s24_featall.py on the data to the year's
end (DIR, default s21h2). Checks: (A) the deployed trees reproduced at their cut (the scores' correlation on the year after >= 0.95;
the recipe: 20/20 identical trees); (B) a new year (>= 300 days after the deployed cut, the data reach it); (D) not broken — finite,
the correlation with the old on the 90 days before the cut >= 0.2, the top 1% above the average label, the threshold within x0.5 .. x2.
-> <out>/vp_dlm_model.json: the file given (BASE: the 4h step's accepted one, else the deployed) with the close2h stream's new trees and
threshold and the model's trained_to; <out>/dlm2h_report.json. usage: YEAR=2027 OUT=dir [BASE=file] python3 ../yearly/yearly_2h.py"""
import os, sys, json, glob, time, calendar, numpy as np, lightgbm as lgb, warnings
warnings.filterwarnings("ignore")
os.environ.setdefault("TFH", "2")
sys.path.insert(0, os.getcwd()); sys.path.append(os.path.join(os.getcwd(), "..", "zones_model"))
import s21h2_engine as E, treevec as TV
from s15_wf import load
from lgbpure import export
ts = lambda y, m=1, d=1: calendar.timegm((y, m, d, 0, 0, 0))
YEAR = int(os.environ["YEAR"]); OUT = os.environ.get("OUT", "yearly_out"); os.makedirs(OUT, exist_ok=True); DIR = os.environ.get("DIR", "s21h2")
ROOT = os.path.join(os.getcwd(), "..", ".."); BASE = os.environ.get("BASE") or os.path.join(ROOT, "vp_dlm_model.json")
M0 = json.load(open(os.path.join(ROOT, "vp_dlm_model.json"))); S0 = [s for s in M0["streams"] if s["name"] == "close2h"][0]
rep = {"model": "dlm2h", "year": YEAR, "ok": False, "checks": {}}
def done(ok, why):
    rep["ok"] = ok; rep["why"] = why
    json.dump(rep, open(os.path.join(OUT, "dlm2h_report.json"), "w"), indent=1, default=float)
    print(("ПРИНЯТО: " if ok else "НЕ ПРИНЯТО: ") + why, flush=True); sys.exit(0 if ok else 3)
fi = E.FAMS.index("d2"); EX = 1
D = load(DIR, [fi]); F2, t2 = [], []
for f in sorted(glob.glob(f"{DIR}/*.npz")):
    z = np.load(f); m = z["fam"] == fi
    if not m.any(): continue
    g = np.load(f"f2_{DIR}/{os.path.basename(f)}"); F2.append(g["F2"][m]); t2.append(g["t"][m])
F2 = np.concatenate(F2); t2 = np.concatenate(t2); assert (t2 == D["t"]).all()
T = D["t"]; TR = ~D["chk"]; y = np.clip(D["R"][EX], -1.5, 1.5)
X1 = D["F"]; X2 = np.concatenate([D["F"], F2[:, [0, 1, 2, 5, 8]]], axis=1)
pr = dict(n_estimators=300, learning_rate=0.05, num_leaves=63, min_child_samples=1000, subsample=0.7, subsample_freq=1, colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
NAMES2 = E.FNAMES + ["d_e20", "d_e50", "d_rsi", "d_pos20", "b_d_e50"]
def fit(cut):
    tr0 = np.flatnonzero(TR & (T < cut)); trees, ms = [], []
    for X in (X1, X2):
        for seed in range(10):
            rng = np.random.default_rng(seed); tr = tr0 if len(tr0) <= 800000 else rng.choice(tr0, 800000, replace=False)
            m = lgb.LGBMRegressor(random_state=seed, **pr).fit(X[tr], y[tr]); trees.append(export(m.booster_, NAMES2[:X.shape[1]])["trees"]); ms.append((X is X2, m))
    return trees, (lambda idx: sum(m.predict((X2 if two else X1)[idx]) for two, m in ms) / len(ms)), len(tr0)
cut0 = int(M0["trained_to"])   # the 2h model's (the 4h streams carry their own)
t0 = time.time()
_, f0, _ = fit(cut0)
te = np.flatnonzero((T >= cut0 + 3 * 86400) & (T < cut0 + 3 * 86400 + 365 * 86400))
a = f0(te); b = TV.model_score(S0["models"], X2[te].astype(float)); cor = float(np.corrcoef(a, b)[0, 1])
ref0 = np.flatnonzero(TR & (T >= cut0 - 365 * 86400) & (T < cut0)); qe = float(np.mean(TV.model_score(S0["models"], X2[ref0].astype(float)) < float(S0["thr"])))
rep["checks"]["A"] = {"corr": round(cor, 4), "q_level": round(qe, 4)}
print(f"(A) 2ч: воспроизведение на старом срезе {time.strftime('%Y-%m-%d', time.gmtime(cut0))}: корреляция {cor:.4f} ({len(te)} событий); порог бота {S0['thr']} = квантиль {qe:.4f} его оценок за год до среза; {time.time() - t0:.0f}s", flush=True)
if cor < 0.95 or not 0.9 <= qe <= 0.9999:
    done(False, f"нынешняя модель 2ч не воспроизвелась (корреляция {cor:.3f}, уровень порога {qe:.4f})")
CUT = ts(YEAR) - 3 * 86400; last = int(T.max())
if os.environ.get("CUT_AT"):   # a rehearsal only
    CUT = int(time.mktime(time.strptime(os.environ["CUT_AT"], "%Y-%m-%d")) - time.timezone)
rep["checks"]["B"] = {"cut": CUT, "old_cut": cut0, "last_event": last}
print(f"(B) срез {time.strftime('%Y-%m-%d', time.gmtime(CUT))}, был {time.strftime('%Y-%m-%d', time.gmtime(cut0))}, последнее событие {time.strftime('%Y-%m-%d', time.gmtime(last))}", flush=True)
if CUT - cut0 < int(os.environ.get("MIN_DAYS", "300")) * 86400 or last < CUT:
    done(False, "нет нового года данных")
trees, f1, n1 = fit(CUT)
ref1 = np.flatnonzero(TR & (T >= CUT - 365 * 86400) & (T < CUT)); thr1 = float(np.quantile(f1(ref1), qe))
w = np.flatnonzero(TR & (T >= CUT - 90 * 86400) & (T < CUT))
o_ = TV.model_score(S0["models"], X2[w].astype(float)); n_ = f1(w)
cor2 = float(np.corrcoef(o_, n_)[0, 1]) if np.std(n_) > 0 else 0.0
sl = f1(ref1); top = sl > np.quantile(sl, 0.99); lift = float(np.mean(y[ref1][top]) - np.mean(y[ref1]))
fin = bool(np.all(np.isfinite(n_)) and np.std(n_) > 0); rt = thr1 / float(S0["thr"])
rep["checks"]["D"] = {"corr_old_new": round(cor2, 4), "top1_lift": round(lift, 4), "finite": fin, "thr_new": thr1, "thr_ratio": round(rt, 3)}
print(f"(D) 2ч: конечные {fin}; корреляция старой и новой на 90 днях {cor2:.3f}; верхний 1% лучше среднего на {lift:+.3f}; порог {S0['thr']} -> {thr1:.4f} (×{rt:.2f}); {time.time() - t0:.0f}s", flush=True)
if not (fin and cor2 >= 0.2 and lift > 0 and 0.5 <= rt <= 2.0):
    done(False, f"новая модель 2ч похожа на сломанную (конечные {fin}, корреляция {cor2:.2f}, выигрыш {lift:+.3f}, порог ×{rt:.2f})")
M = json.load(open(BASE))
for s in M["streams"]:
    if s["name"] == "close2h":
        s["models"] = trees; s["thr"] = round(thr1, 6)
M["trained_to"] = int(CUT); M.setdefault("retrained", {}).update({"close2h": {"by": "yearly fallback (GitHub Actions)", "t": int(time.time()), "events": n1}})
json.dump(M, open(os.path.join(OUT, "vp_dlm_model.json"), "w"), separators=(",", ":"))
done(True, f"поток 2ч переобучен по {time.strftime('%d.%m.%Y', time.gmtime(CUT))} ({n1} событий), порог {S0['thr']} → {thr1:.4f} на прежнем уровне")
