"""the deployed EMA model's own threshold at another q: its trees (vectorised) over the last 365 days of touches, as
er_export2.py set "thr" (q 0.97 must give back the model's thr)"""
import json, sys, numpy as np, pandas as pd
sys.setrecursionlimit(10000)
from common import D
m = json.load(open("/home/user/vp-poc-screener/vp_ema_model.json"))
d = pd.read_parquet(f"{D}/er_all.parquet", columns=["t"] + m["feats"])
T = d.t.values; last = T >= T.max() - 365 * 86400
X = d.loc[last, m["feats"]].values.astype(np.float64)
def ev(t, idx, out):
    if not isinstance(t, list): out[idx] += t; return
    if not len(idx): return
    v = X[idx, t[0]]; go = np.where(np.isnan(v), t[2] == 1, v <= t[1])
    ev(t[3], idx[go], out); ev(t[4], idx[~go], out)
sc = np.zeros(len(X)); allidx = np.arange(len(X))
for trees in m["models"]:
    for t in trees: ev(t, allidx, sc)
sc /= len(m["models"])
for q in (0.97, 0.965, 0.96, 0.955, 0.95): print(q, round(float(np.quantile(sc, q)), 6), "(model thr", m["thr"], ")" if q == 0.97 else "")
