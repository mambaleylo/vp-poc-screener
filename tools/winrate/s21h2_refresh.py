"""⚡ 2h: is a mid-year refresh worth it? (HANDOFF "Дальше" 2: the deployed recipe retrained with the data up to October).
A model trained to month c can be judged honestly only after c, so: the deployed close2h trees (trained to 2025-12-29) vs the
same recipe (s21h2_repro.py: fam d2, E1 clipped +-1.5, 10 seeds x 28 + 10 x 33 features, the train coins, events closed 3 days
before c) retrained at each cut c in CUTS; both scored on the events from c to the data's end — out of sample for both.
The refreshed model's threshold: the deployed thr's quantile among the deployed scores of the train coins' 365 days before c,
taken at the same quantile of the refreshed model's own scores there (a rule the bot could follow). Trades as dlm_roll_cmp:
score >= thr, one per coin & side until its exit, at most 20 a side. Also the top-N match (the refreshed model allowed the
deployed's trade count). Last: the model trained to the data's end saved (s21h2_refresh_final.json) for a later export.
usage: s21h2_refresh.py [NS] [CUTS e.g. 2026-04,2026-07] [FINAL 0/1]"""
import sys; AV = list(sys.argv)
import os, glob, json, calendar, numpy as np, lightgbm as lgb, warnings; warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.append(os.path.join(HERE, "..", "zones_model"))
os.environ.setdefault("TFH", "2")
import s21h2_engine as E, treevec as TV
from s15_wf import load
from lgbpure import export
NS = int(AV[1]) if len(AV) > 1 else 10
CUTS = [tuple(map(int, c.split("-"))) for c in (AV[2] if len(AV) > 2 else "2026-04,2026-07").split(",")]
FINAL = int(AV[3]) if len(AV) > 3 else 1
ts = lambda y, m=1, d=1: calendar.timegm((y, m, d, 0, 0, 0))
M = json.load(open(os.path.join(HERE, "..", "..", "vp_dlm_model.json"))); S = [s for s in M["streams"] if s["name"] == "close2h"][0]
fi = E.FAMS.index("d2"); EX = 1
D = load("s21h2", [fi]); F2 = []
for f in sorted(glob.glob("s21h2/*.npz")):
    z = np.load(f); m = z["fam"] == fi
    if m.any(): F2.append(np.load(f"f2_s21h2/{os.path.basename(f)}")["F2"][m])
F2 = np.concatenate(F2)
T, SD, SYM, K, R = D["t"], D["side"], D["sym"], D["K"][EX], D["R"][EX]; TR = ~D["chk"]; y = np.clip(R, -1.5, 1.5)
X1 = D["F"]; X2 = np.concatenate([D["F"], F2[:, [0, 1, 2, 5, 8]]], axis=1)
# the label needs the exit inside the data: the events closed (K hours) before the last bar
# (EVAL_END=2026-10-28: Binance has no daily archive of 2026-10-28 — the events up to that hole only)
END = ts(*map(int, os.environ["EVAL_END"].split("-"))) if os.environ.get("EVAL_END") else int(T.max())
OK = T + K.astype(np.int64) * 3600 <= END
print(f"событий d2: {len(T)}, последнее {np.datetime64(END, 's')}, проверочных монет {len(set(SYM[~TR]))} из {len(D['names'])}", flush=True)
pr = dict(n_estimators=300, learning_rate=0.05, num_leaves=63, min_child_samples=1000, subsample=0.7, subsample_freq=1,
          colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)

def train(cut, idx_score):
    tr0 = np.flatnonzero(TR & (T < cut - 3 * 86400) & OK); models = []; sc = np.zeros(len(idx_score))
    for X in (X1, X2):
        for seed in range(NS):
            rng = np.random.default_rng(seed); tr = tr0 if len(tr0) <= 800000 else rng.choice(tr0, 800000, replace=False)
            m = lgb.LGBMRegressor(random_state=seed, **pr).fit(X[tr], y[tr])
            models.append(export(m.booster_, E.FNAMES + ["d_e20", "d_e50", "d_rsi", "d_pos20", "b_d_e50"][:X.shape[1] - 28])["trees"])
            sc += m.predict(X[idx_score]) / (2 * NS)
    return models, sc, len(tr0)

def pool(idx, sc, thr):
    """the trades: score >= thr, by time then score, one per coin & side until its exit, at most 20 a side"""
    i = idx[sc >= thr]; s = sc[sc >= thr]; o = i[np.lexsort((-s, T[i]))]; busy = {}; act = []; out = []
    for j in o:
        t = T[j]; key = (SYM[j], SD[j])
        if busy.get(key, 0) > t: continue
        act = [x for x in act if x[0] > t]
        if sum(1 for x in act if x[1] == SD[j]) >= 20: continue
        e = t + int(K[j]) * 3600; busy[key] = e; act.append((e, SD[j])); out.append(j)
    return np.array(out, np.int64)

def line(nm, sel):
    if not len(sel): return f"{nm}: сделок нет"
    r = R[sel]; c = np.cumsum(r[np.argsort(T[sel])]); dd = float(np.max(np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c]))
    tr, ch = TR[sel], ~TR[sel]
    return (f"{nm}: {len(sel)} сделок, WR {(r > 0).mean() * 100:.0f}%, {r.mean():+.3f}R, Σ{r.sum():+.0f}R, просадка {dd:.0f}R | "
            f"обуч. монеты {tr.sum()} {r[tr].mean() if tr.any() else 0:+.3f}R | проверочные {ch.sum()} {r[ch].mean() if ch.any() else 0:+.3f}R")

dep_all = TV.model_score(S["models"], X2.astype(float))
for (cy, cm) in CUTS:
    c = ts(cy, cm); te = np.flatnonzero((T >= c) & OK); ref = TR & (T >= c - 365 * 86400) & (T < c)
    models, sc, ntr = train(c, np.r_[te, np.flatnonzero(ref)]); sc_te, sc_ref = sc[:len(te)], sc[len(te):]
    q = (dep_all[ref] < S["thr"]).mean(); thr_new = np.quantile(sc_ref, q)
    print(f"\n== обновление {cy}-{cm:02d} (обучено на {ntr}), проверка {np.datetime64(c, 's')} .. {np.datetime64(END, 's')}: {len(te)} событий; "
          f"порог бота {S['thr']} = квантиль {q:.4f} его оценок за год до → у обновлённой {thr_new:.4f}", flush=True)
    a = pool(te, dep_all[te], S["thr"]); b = pool(te, sc_te, thr_new)
    print(line("как в боте (обучена до 2025-12)", a), flush=True)
    print(line("обновлённая, свой порог", b), flush=True)
    k = len(a)
    # top-N match: lower / raise the refreshed model's threshold until it makes the deployed's trade count
    lo, hi = float(sc_te.min()), float(sc_te.max())
    for _ in range(40):
        mid = (lo + hi) / 2
        if len(pool(te, sc_te, mid)) > k: lo = mid
        else: hi = mid
    print(line(f"обновлённая, столько же сделок (порог {hi:.4f})", pool(te, sc_te, hi)), flush=True)
    rho = np.corrcoef(dep_all[te], sc_te)[0, 1]
    for qq in (0.99, 0.97):
        ta, tb = dep_all[te] >= np.quantile(dep_all[te], qq), sc_te >= np.quantile(sc_te, qq)
        print(f"верхние {100 - qq * 100:.0f}% событий: R бот {R[te][ta].mean():+.3f} / обновлённая {R[te][tb].mean():+.3f}; общих {(ta & tb).sum() / ta.sum() * 100:.0f}%; корреляция оценок {rho:.3f}", flush=True)
if FINAL:
    models, _, ntr = train(END + 3 * 86400, np.arange(1))
    ref = TR & (T >= END - 365 * 86400); sc = TV.model_score(models, X2[ref].astype(float)); q = (dep_all[ref] < S["thr"]).mean()
    json.dump({"models": models, "trained_to": str(np.datetime64(END - 3 * 86400, 'D')), "thr_q": float(q), "thr": float(np.quantile(sc, q))},
              open("s21h2_refresh_final.json", "w"))
    print(f"итоговая модель до {np.datetime64(END, 'D')} ({ntr} событий) сохранена, порог {np.quantile(sc, q):.4f}", flush=True)
print("refresh done", flush=True)
