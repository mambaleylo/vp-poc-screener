"""The yearly fallback — 📏 HTF: the deployed recipe (htf_export.py) with the cut as a parameter — two models on the SMC lab's events
(lv2): "o" = the HTF levels (fam <= 22, both sides), label E2; "n" = the long HTF touches (2019+), label = the traded exit (soft
stop 1 dATR at a 4h close, hard 3 dATR, take 3R, 96 h); 2 LightGBM each (seeds 0 / 1) on the bot coins' events closed 14 days
before the cut; each threshold the walk-forward way: the order statistic q of the year before's OUT-OF-SAMPLE scores of its own
events (htf_sc.py / lv_wf.scores). Run in tools/winrate with LVDIR / LV_D1H = the events and their candles. Checks: (A) the deployed
models reproduced at their cut (each correlation on the year after's long HTF touches >= 0.90; the recipe: 0.973 / 0.976), the
thresholds within 15%; (B) a new year; (D) not broken — finite, correlation with the old >= 0.2, the top 1% above the average label,
the new thresholds within x0.5 .. x2. -> <out>/vp_htf_model.json, <out>/htf_report.json.
usage: YEAR=2027 OUT=dir LVDIR=dir LV_D1H=dir python3 ../yearly/yearly_htf.py"""
import os, sys, json, glob, math, time, numpy as np, lightgbm as lgb, warnings
warnings.filterwarnings("ignore")
HERE = os.getcwd(); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "new_ind")); sys.path += [os.path.join(HERE, "..", "zones_model"), os.path.join(HERE, "..", "neuro_model")]
from numba import njit
import types; sys.modules.setdefault("nx_h", types.SimpleNamespace(pain=None))
from lv_wf import load_dir, ts
import lv_engine as LE, treevec as TV
from lgbpure import export
YEAR = int(os.environ["YEAR"]); OUT = os.environ.get("OUT", "yearly_out"); os.makedirs(OUT, exist_ok=True); LVDIR = os.environ.get("LVDIR", "lv2")
ROOT = os.path.join(HERE, "..", ".."); M0 = json.load(open(os.path.join(ROOT, "vp_htf_model.json")))
rep = {"model": "htf", "year": YEAR, "ok": False, "checks": {}}
def done(ok, why):
    rep["ok"] = ok; rep["why"] = why
    json.dump(rep, open(os.path.join(OUT, "htf_report.json"), "w"), indent=1, default=float)
    print(("ПРИНЯТО: " if ok else "НЕ ПРИНЯТО: ") + why, flush=True); sys.exit(0 if ok else 3)
Dd = load_dir(LVDIR, LE.FNAMES); F = Dd["F"]; fam = F[:, 0].astype(int); T, SIDE, SYM, BOT = Dd["T"], Dd["SIDE"], Dd["SYM"], Dd["BOT"]
LV, J, DT = [], [], []
for fn in sorted(glob.glob(f"{LVDIR}/*.npz")):
    z = np.load(fn)
    if len(z["t"]) == 0: continue
    LV.append(z["lv"]); J.append(z["j"]); DT.append(z["datr"])
LV, J, DATR = np.concatenate(LV), np.concatenate(J).astype(np.int64), np.concatenate(DT)
@njit
def wk2(O, H, L, C, Tb, j, fill, datr, hard_a, take, hold, kh):   # = htf_repro.py / htf_export.py
    risk = fill * datr / 100; ssl = fill - risk; hsl = fill - hard_a * risk; tp = fill + take * risk
    n = len(C); e = min(n, j + hold)
    for q in range(e - j):
        b = j + q
        if L[b] <= hsl:
            x = O[b] if (q > 0 and O[b] <= hsl) else hsl
            return (x - fill) / risk - (0.001 + 0.0003 * (q + 1) / 24) * fill / risk
        if q > 0 and H[b] >= tp:
            return (tp - fill) / risk - (0.001 + 0.0003 * (q + 1) / 24) * fill / risk
        if (Tb[b] + 3600) % (kh * 3600) == 0 and C[b] <= ssl:
            return (C[b] - fill) / risk - (0.001 + 0.0003 * (q + 1) / 24) * fill / risk
    b = e - 1
    return (C[b] - fill) / risk - (0.001 + 0.0003 * (e - j) / 24) * fill / risk
HTF = fam <= 22
LONG = HTF & (SIDE > 0) & (T >= ts(2019)) & np.isfinite(DATR)
RL = np.full(len(T), np.nan); idx = np.flatnonzero(LONG)
for k in sorted(set(SYM[idx])):
    Tb, O, H, L, C, V = LE.load_np(Dd["names"][k])
    for i in idx[SYM[idx] == k]:
        if J[i] < len(C): RL[i] = wk2(O, H, L, C, Tb, int(J[i]), float(LV[i]), float(DATR[i]), 3.0, 3.0, 96, 4)
Q = float(M0.get("q", 0.995))
pr = dict(n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=300, subsample=0.7, subsample_freq=1, colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
SETS = {"o": (HTF, np.nan_to_num(Dd["R"][2], nan=0.0).clip(-1.2, 6.0)), "n": (LONG, np.nan_to_num(RL, nan=0.0).clip(-1.2, 6.0))}
def fit(key, cut):
    mask, y = SETS[key]; tr = mask & BOT & (T < cut); trees, ms = [], []
    for s in range(2):
        m = lgb.LGBMRegressor(random_state=s, **pr).fit(F[tr], y[tr]); trees.append(export(m.booster_, LE.FNAMES)["trees"]); ms.append(m)
    return trees, (lambda X: sum(m.predict(X) for m in ms) / 2), int(tr.sum())
def thr_of(key, cut_new, f_prev, lo=None):
    """the order statistic q of the previous model's out-of-sample scores on its events of the year before the new cut"""
    mask, _ = SETS[key]; yb = time.gmtime(cut_new + 14 * 86400).tm_year
    ref = np.flatnonzero(mask & BOT & (T >= (lo if lo is not None else ts(yb - 1))) & (T < cut_new))
    if len(ref) < 200: return None, len(ref)
    v = np.sort(f_prev(F[ref])); return float(v[math.ceil(Q * len(v)) - 1]), len(ref)
cut0 = int(M0["trained_to"]); y0 = time.gmtime(cut0 + 14 * 86400).tm_year
te = np.flatnonzero(LONG & BOT & (T >= cut0 + 14 * 86400) & (T < cut0 + 14 * 86400 + 365 * 86400))
CUT = ts(YEAR) - 14 * 86400; last = int(T.max()); reh = bool(os.environ.get("CUT_AT"))
if reh:   # a rehearsal only (the data end before the year)
    CUT = int(time.mktime(time.strptime(os.environ["CUT_AT"], "%Y-%m-%d")) - time.timezone)
new = {}; A = {}; D = {}
for key in ("o", "n"):
    _, f0, _ = fit(key, cut0)
    a = f0(F[te]); b = TV.model_score(M0["models_" + key], F[te].astype(float)); cor = float(np.corrcoef(a, b)[0, 1])
    _, fpp, _ = fit(key, ts(y0 - 1) - 14 * 86400); t0r, nr = thr_of(key, cut0, fpp); t0 = float(M0["thr_" + key])
    A[key] = {"corr": round(cor, 4), "thr_deployed": t0, "thr_rebuilt": t0r, "ref": nr}
    print(f"(A) модель {key}: корреляция на старом срезе {cor:.4f} ({len(te)} длинных касаний); порог бота {t0:.4f}, пересобранный {t0r if t0r is None else round(t0r, 4)} ({nr})", flush=True)
    if cor < 0.90 or (t0r is not None and abs(t0r - t0) > 0.15 * abs(t0)):
        rep["checks"]["A"] = A; done(False, f"модель {key} не воспроизвелась (корреляция {cor:.3f}, порог {t0r} против {t0:.4f})")
    if key == "o":
        rep["checks"]["B"] = {"cut": CUT, "old_cut": cut0, "last_event": last}
        print(f"(B) срез {time.strftime('%Y-%m-%d', time.gmtime(CUT))}, был {time.strftime('%Y-%m-%d', time.gmtime(cut0))}, последнее событие {time.strftime('%Y-%m-%d', time.gmtime(last))}", flush=True)
        if CUT - cut0 < int(os.environ.get("MIN_DAYS", "300")) * 86400 or last < CUT:
            rep["checks"]["A"] = A; done(False, "нет нового года данных")
    trees, f1, n1 = fit(key, CUT)
    t1, _ = thr_of(key, CUT, f0, lo=(cut0 + 14 * 86400) if reh else None)
    mask, y = SETS[key]
    w = np.flatnonzero(mask & BOT & (T >= CUT - 90 * 86400) & (T < CUT))
    o_ = TV.model_score(M0["models_" + key], F[w].astype(float)); n_ = f1(F[w])
    cor2 = float(np.corrcoef(o_, n_)[0, 1]) if np.std(n_) > 0 else 0.0
    ly = np.flatnonzero(mask & BOT & (T >= CUT - 365 * 86400) & (T < CUT)); sl = f1(F[ly]); top = sl > np.quantile(sl, 0.99)
    lift = float(np.mean(y[ly][top]) - np.mean(y[ly])); fin = bool(np.all(np.isfinite(n_)) and np.std(n_) > 0)
    rt = (t1 / t0) if (t1 and t0) else 0.0
    D[key] = {"corr_old_new": round(cor2, 4), "top1_lift": round(lift, 4), "finite": fin, "thr_new": t1, "thr_ratio": round(rt, 3)}
    print(f"(D) модель {key}: конечные {fin}; корреляция старой и новой на 90 днях {cor2:.3f}; верхний 1% лучше среднего на {lift:+.3f}; порог {t0:.4f} -> {t1 if t1 is None else round(t1, 4)} (×{rt:.2f})", flush=True)
    if not (fin and cor2 >= 0.2 and lift > 0 and 0.5 <= rt <= 2.0):
        rep["checks"]["A"] = A; rep["checks"]["D"] = D
        done(False, f"новая модель {key} похожа на сломанную (конечные {fin}, корреляция {cor2:.2f}, выигрыш {lift:+.3f}, порог ×{rt:.2f})")
    new[key] = (trees, t1, n1)
rep["checks"]["A"] = A; rep["checks"]["D"] = D
M = dict(M0, models_o=new["o"][0], thr_o=new["o"][1], models_n=new["n"][0], thr_n=new["n"][1], trained_to=int(CUT),
         thr_from=f"{time.gmtime(CUT + 14 * 86400).tm_year - 1} out of sample of each model, q {Q:g} — the yearly fallback",
         retrained={"by": "yearly fallback (GitHub Actions)", "t": int(time.time()), "events": [new["o"][2], new["n"][2]]})
json.dump(M, open(os.path.join(OUT, "vp_htf_model.json"), "w"), separators=(",", ":"))
rep["trained_to"] = int(CUT)
done(True, f"переобучена по {time.strftime('%d.%m.%Y', time.gmtime(CUT))}, пороги o {M0['thr_o']:.3f} → {new['o'][1]:.3f}, n {M0['thr_n']:.3f} → {new['n'][1]:.3f}, правило прежнее")
