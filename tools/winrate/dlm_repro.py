"""is ⚡'s deployed model reproducible by this lab (the user: "сопоставить... для лимиток тоже перепроверить")? Its trees
(trained to 2025-12-29) score the 2026 orders of every 10th coin; this lab's 2026 walk-forward model (dlm_wf2 var_y_all:
the same cut-off, the train coins) scored them too -> the correlation and the overlap of the chosen (over the threshold)"""
import json, glob, os, sys, numpy as np, treevec as TV, calendar
m = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "vp_dlm_model.json"))); ST = "/home/user/vp-lab-store"
t26 = calendar.timegm((2026, 1, 1, 0, 0, 0))
for st in ("wick4h", "close2h"):
    S = [s for s in m["streams"] if s["name"] == st][0]
    FL = [[TV.flat(t) for t in mm] for mm in S["models"]]
    z = np.load(f"{ST}/wf/var_y_all/scores_{st}.npz", allow_pickle=True); k = z["t"] >= t26
    key = {(str(c), int(t), int(s)): (sc, th, r) for c, t, s, sc, th, r in zip(z["coin"][k], z["t"][k], z["side"][k], z["score"][k], z["thr"][k], z["R"][k])}
    A, B, TH, RR = [], [], [], []
    for fn in sorted(glob.glob(f"{ST}/feat/{st}/*.npz"))[::10]:
        c = os.path.basename(fn)[:-4]; f = np.load(fn, allow_pickle=True); w = f["t"] >= t26
        if not w.any(): continue
        d = np.mean([TV.predict(mm, f["F"][w]) for mm in FL], axis=0)
        for t, s, x in zip(f["t"][w], f["side"][w], d):
            v = key.get((c, int(t), int(s)))
            if v is not None: A.append(x); B.append(v[0]); TH.append(v[1]); RR.append(v[2])
        print(c, len(A), flush=True)
    A, B, TH, RR = np.array(A), np.array(B), np.array(TH), np.array(RR, float)
    sa, sb = A >= S["thr"], B >= TH
    f_ = lambda m_: f"{np.nanmean(RR[m_ & np.isfinite(RR)]):+.3f}R из {int((m_ & np.isfinite(RR)).sum())} исполненных"
    print(f"R {st}: отбор бота {f_(sa)}; отбор пересборки {f_(sb)}; только бот {f_(sa & ~sb)}; только пересборка {f_(sb & ~sa)}", flush=True)
    print(f"ИТОГ {st}: ордеров 2026 {len(A)}, корреляция оценок {np.corrcoef(A, B)[0, 1]:.4f}; выше порога: бот {sa.sum()}, пересборка {sb.sum()}, общих {(sa & sb).sum()}", flush=True)
print("repro done", flush=True)
