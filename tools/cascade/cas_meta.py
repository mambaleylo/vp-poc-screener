"""🌊 cascade — an entry filter against losing trades (the user: "фильтры, чтобы именно вход даже в такие сделки
ограничивался"): meta-labelling. A second model, trained only on the cascade's own candidates (the score above the
q 0.98 threshold of its year), learns P(the trade loses) under the deployed rule (a third at +0.7R, take 2.5R, 48 h);
walk-forward by year (trained on the years before - 10 days); a candidate is skipped when its P(loss) is in the top
k% of the previous year's candidates. Judged on the bot's set (q 0.995) and the check set (q 0.98)."""
import os, sys
os.environ.setdefault("CAS_SEL", "cas_sel_base3.npz")
import numpy as np, lightgbm as lgb
from cas_h import S, SD, T, X
from cas_loss import show
from mk import ts
lab = np.load("cas_lab_part.npy")
cand = np.zeros(len(T), bool)
for s in (1, -1):
    sc = S[f"sc_sw_t2_48_{s}"]; tv = S[f"thrv_sw_t2_48_{s}_0.98"]
    cand |= (SD == s) & ~np.isnan(sc) & (sc >= tv)
cand &= ~np.isnan(lab)
print("кандидатов", cand.sum(), "минусовых", np.mean(lab[cand] < 0).round(3), flush=True)
P = np.full(len(T), np.nan)
QS = (0.7, 0.8, 0.9)
THR = {q: np.full(len(T), np.inf) for q in QS}
for y in range(2022, 2027):
    tr = cand & (T < ts(y) - 10 * 86400); te = cand & (T >= ts(y)) & (T < ts(y + 1)); ref = cand & (T >= ts(y - 1)) & (T < ts(y) - 10 * 86400)
    if tr.sum() < 500 or not te.any(): continue
    ms = [lgb.LGBMClassifier(n_estimators=200, learning_rate=0.03, num_leaves=7, min_child_samples=100, subsample=0.8, subsample_freq=1,
                             colsample_bytree=0.5, reg_lambda=10.0, verbose=-1, n_jobs=4, random_state=k).fit(X[tr], (lab[tr] < 0).astype(int)) for k in range(3)]
    pr = lambda m_: sum(m.predict_proba(X[m_])[:, 1] for m in ms) / len(ms)
    P[te] = pr(te); pref = pr(ref)
    for q in QS: THR[q][te] = np.quantile(pref, q)
    # how well it ranks on the test year: the loss rate in the riskiest / safest fifth
    p = P[te]; l = lab[te] < 0; hi = p >= np.quantile(p, 0.8); lo = p <= np.quantile(p, 0.2)
    print(y, f"минусов: самые рискованные 20% — {l[hi].mean()*100:.0f}%, самые безопасные 20% — {l[lo].mean()*100:.0f}%, все — {l.mean()*100:.0f}%", flush=True)
np.save("cas_meta_p.npy", P)
show("сейчас", {})
for q in QS:
    keep = ~(P >= THR[q])
    show(f"пропуск {round((1 - q) * 100)}% самых рискованных", {"mask": keep})
