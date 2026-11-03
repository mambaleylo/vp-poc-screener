"""The market's regime by a hidden Markov model (the user: "цепи Маркова … режимы рынка", then "хочу"): every 4 h of 2021-2026
the observations — BTC's 4 h log return, BTC's last-24 h volatility (the std of its hourly returns), the market's mean 24 h
return and the share of coins down > 5% minus up > 5% (breadth_build.py) — a 3-state Gaussian HMM fitted per year on everything
before the year (walk-forward), the states named by their BTC volatility (calm / active / panic); the probabilities by the
FORWARD pass only (filtering: the bar's own and the earlier observations — no look-ahead, unlike hmmlearn's predict_proba).
-> <LABSTORE>/wf/hmm_regime.npz: T (the 4 h bar's close = when it is known), p_calm, p_act, p_panic, the year's model id"""
import os, calendar, numpy as np, warnings
from hmmlearn.hmm import GaussianHMM
from scipy.special import logsumexp
warnings.filterwarnings("ignore")
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
ts = lambda y: calendar.timegm((y, 1, 1, 0, 0, 0))
import gzip
a = np.loadtxt(gzip.open(f"{ST}/data/1h/BTCUSDT.csv.gz", "rt"), delimiter=",", usecols=(0, 4)); T1, C1 = a[:, 0].astype(np.int64), a[:, 1]
B = np.load(f"{ST}/wf/breadth.npz")
r1 = np.diff(np.log(C1), prepend=np.log(C1[0]))
T4 = np.arange(ts(2021) + 4 * 86400, int(min(T1[-1], B["T"][-1])) - 4 * 3600, 4 * 3600, dtype=np.int64)   # the 4 h bars' open
def at1h(t):   # the index of the hour starting at t (its close = t + 1h)
    return np.clip(np.searchsorted(T1, t, side="right") - 1, 0, len(T1) - 1)
i_end = at1h(T4 + 3 * 3600)   # the bar's last hour
i_beg = at1h(T4 - 3600)
ret4 = np.log(C1[i_end]) - np.log(C1[i_beg])
vol24 = np.array([np.std(r1[max(0, j - 23):j + 1]) for j in i_end])
jb = np.clip((T4 + 3 * 3600 - B["T"][0]) // 3600, 0, len(B["T"]) - 1)
X = np.column_stack([ret4, np.log(vol24 + 1e-5), B["r24"][jb], B["dn5"][jb] - B["up5"][jb]])
TC = T4 + 4 * 3600   # known at the bar's close
P = np.full((len(TC), 3), np.nan); YID = np.zeros(len(TC), np.int64)
for Y in range(2022, 2027):
    tr = TC < ts(Y); te = (TC >= ts(Y)) & (TC < ts(Y + 1))
    if tr.sum() < 1000 or not te.any(): continue
    mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9; Z = (X - mu) / sd
    best = None
    for seed in range(5):
        m = GaussianHMM(n_components=3, covariance_type="full", n_iter=300, random_state=seed, tol=1e-4).fit(Z[tr])
        ll = m.score(Z[tr])
        if best is None or ll > best[0]: best = (ll, m)
    m = best[1]
    order = np.argsort(m.means_[:, 1])   # by BTC's volatility: calm, active, panic
    # the forward pass over everything up to the year's end (causal), the year's rows kept
    lb = m._compute_log_likelihood(Z[:np.flatnonzero(te)[-1] + 1])
    la = np.log(m.startprob_ + 1e-300) + lb[0]; lt = np.log(m.transmat_ + 1e-300); out = np.empty_like(lb); out[0] = la - logsumexp(la)
    for t in range(1, len(lb)):
        la = logsumexp(out[t - 1][:, None] + lt, axis=0) + lb[t]; out[t] = la - logsumexp(la)
    idx = np.flatnonzero(te); P[idx] = np.exp(out[idx])[:, order]; YID[idx] = Y
    st = np.argmax(P[idx], 1)
    print(Y, "доля режимов (спокойный / активный / паника):", [round(float((st == k).mean()), 3) for k in range(3)],
          "| средняя доходность BTC за 4ч по режимам:", [round(float(ret4[idx][st == k].mean() * 100), 3) if (st == k).any() else None for k in range(3)],
          "| переход в панику остаётся:", round(float(m.transmat_[order[2], order[2]]), 3), flush=True)
np.savez_compressed(f"{ST}/wf/hmm_regime.npz", T=TC, p_calm=P[:, 0], p_act=P[:, 1], p_panic=P[:, 2], year=YID)
for d in ("2023-03-10", "2024-03-05", "2025-10-10", "2025-10-11"):
    t = int(np.datetime64(d + "T12:00:00", "s").astype(np.int64)); i = np.searchsorted(TC, t)
    print(d, "вероятности (спокойный / активный / паника):", np.round(P[i], 3), flush=True)
print("hmm done", flush=True)
