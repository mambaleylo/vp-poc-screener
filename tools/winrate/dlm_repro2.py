"""⚡'s deployed model vs the lab's 20-model ensemble (dlm_wf2's recipe with NS=10: 10 seeds x the 28 / 33 features, the
train coins' orders closed 3 days before 2026, the label R clipped to +-1.5) on every coin's 2026 orders: the lab scores
all of them; the deployed trees (slow) only the lab's top 20% (its picks — the top ~1% — are inside: the scores correlate
~0.9). The same number of picks each (the deployed threshold's count) -> the R of the bot's picks, the lab's, each one's own"""
import os, sys, json, time, glob, calendar, numpy as np, lightgbm as lgb, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import treevec as TV
from common import V   # dlm_wf2 maps the research coins with the bot's list
ST = "/home/user/vp-lab-store"; ts = lambda y, m=1, d=1: calendar.timegm((y, m, d, 0, 0, 0)); A = ts(2026)
sys.argv = sys.argv[:1] + ["x", "0", "12"]
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dlm_wf2.py")).read()
exec(src[src.index("C = json.load"):src.index("OUT = f")])   # GROUP, pr — exactly dlm_wf2's
M = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "vp_dlm_model.json")))
for stream in ("wick4h", "close2h"):
    S = [s for s in M["streams"] if s["name"] == stream][0]
    rows = {k: [] for k in ("coin", "t", "side", "F", "R", "tout")}
    for c, g in GROUP.items():
        fn = f"{ST}/feat/{stream}/{c}.npz"
        if not os.path.exists(fn): continue
        z = np.load(fn)
        if not len(z["t"]): continue
        rows["coin"].append(np.full(len(z["t"]), c))
        for k in ("t", "side", "F", "R", "tout"): rows[k].append(z[k])
    D = {k: np.concatenate(v) for k, v in rows.items()}
    TR = np.array([GROUP[c] == "train" for c in D["coin"]]); T = D["t"]; F = D["F"]
    tr = np.flatnonzero(TR & (D["tout"] < A - 3 * 86400)); te = np.flatnonzero((T >= A) & (T < ts(2026, 11)))
    yv = np.clip(D["R"], -1.5, 1.5); sc = np.zeros(len(te)); k = 0; t0 = time.time()
    for X in (F[:, :28], F):
        for seed in range(10):
            sc += lgb.LGBMRegressor(random_state=seed, **pr).fit(X[tr], yv[tr]).predict(X[te]); k += 1
    sc /= k
    print(f"{stream}: 20 моделей обучены ({time.time() - t0:.0f}s), ордеров 2026 {len(te)}", flush=True)
    top = te[sc >= np.quantile(sc, 0.8)]; sct = sc[sc >= np.quantile(sc, 0.8)]
    FL = [[TV.flat(t) for t in mm] for mm in S["models"]]
    bot = np.mean([TV.predict(mm, F[top]) for mm in FL], axis=0)
    nb = int((bot >= S["thr"]).sum())
    pb = top[np.argsort(-bot)[:nb]]; pl = top[np.argsort(-sct)[:nb]]
    R = D["R"]
    f_ = lambda ix: f"{np.nanmean(R[ix]):+.3f}R ({np.isfinite(R[ix]).sum()} исп.)" if len(ix) else "—"
    sb, sl = set(pb.tolist()), set(pl.tolist())
    print(f"ИТОГ {stream}: отбор бота {nb}: {f_(pb)} | отбор пересборки {nb}: {f_(pl)} | общих {len(sb & sl)} | только бот {f_(np.array(sorted(sb - sl)))} | "
          f"только пересборка {f_(np.array(sorted(sl - sb)))} | корреляция в лучших 20% {np.corrcoef(bot, sct)[0, 1]:.3f}", flush=True)
print("repro2 done", flush=True)
