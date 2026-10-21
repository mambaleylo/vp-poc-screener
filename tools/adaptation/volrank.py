"""point-in-time liquidity: each coin's 30-day quote volume (Binance 1h) at every day, its rank among the 211 coins ->
rank_at(sym_array, t_array) (1 = the most traded; the bot trades Gate's top-N by 24h volume)"""
import numpy as np, os
from common import load
_R = {}
def _build():
    syms = sorted(f[:-4] for f in os.listdir("data/1h"))
    day0, day1 = 1577836800 // 86400, 1790900000 // 86400
    V = np.zeros((len(syms), day1 - day0 + 1))
    for k, s in enumerate(syms):
        for c in load(s) or []:
            d = c["time"] // 86400 - day0
            if 0 <= d < V.shape[1]: V[k, d] += c.get("volume", 0.0) or 0.0
    cs = np.cumsum(V, axis=1); v30 = cs - np.concatenate([np.zeros((len(syms), 30)), cs[:, :-30]], axis=1)
    v30 = np.concatenate([np.zeros((len(syms), 1)), v30[:, :-1]], axis=1)          # up to the day before
    order = np.argsort(-v30, axis=0); rank = np.empty_like(order); rank[order, np.arange(v30.shape[1])[None, :]] = np.arange(len(syms))[:, None] + 1
    rank = np.where(v30 > 0, rank, 9999)
    _R.update(syms={s: k for k, s in enumerate(syms)}, rank=rank, day0=day0)
def rank_at(syms, ts_):
    if not _R: _build()
    idx = np.array([_R["syms"].get(str(s), -1) for s in syms]); d = np.clip(np.asarray(ts_) // 86400 - _R["day0"], 0, _R["rank"].shape[1] - 1)
    return np.where(idx >= 0, _R["rank"][np.maximum(idx, 0), d], 9999)
