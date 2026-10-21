"""Open interest / long-short / taker features from data/metrics/<SYM>.csv (dl_metrics.py), per coin and closed hour.
at(syms, H) -> (n, k) float32 for the hour rows H (the hour's open, unix s; the row = the last 5-min values of that hour,
known at its close), NaN where there is no data. NAMES; DIR = the ones read in the trade's direction (× side)."""
import os, numpy as np
NAMES = ["oi1", "oi4", "oi24", "oi72", "oi_rel30", "top_acc", "top_pos", "ls_acc", "ls_d24", "tk1", "tk4", "tk24", "smart"]
DIR = {"top_acc", "top_pos", "ls_acc", "ls_d24", "tk1", "tk4", "tk24", "smart"}
_C = {}
def _lag(t, x, h):
    j = np.searchsorted(t, t - h * 3600); j = np.minimum(j, len(t) - 1)
    ok = t[j] == t - h * 3600
    return np.where(ok, x[j], np.nan)
def coin(sym):
    if sym in _C: return _C[sym]
    fn = f"data/metrics/{sym}.csv"
    if not os.path.exists(fn): _C[sym] = None; return None
    a = np.genfromtxt(fn, delimiter=",", skip_header=1)
    if a.ndim < 2 or not len(a): _C[sym] = None; return None
    t = a[:, 0].astype(np.int64); oi, ta, tp, ls, tk = (np.where(a[:, k] > 0, a[:, k], np.nan) for k in (1, 3, 4, 5, 6))
    loi, lta, ltp, lls, ltk = np.log(oi), np.log(ta), np.log(tp), np.log(ls), np.log(tk)
    c = np.nancumsum(np.nan_to_num(oi)); n30 = 720
    m30 = (c - np.r_[np.zeros(n30), c[:-n30]]) / np.minimum(np.arange(1, len(c) + 1), n30)
    def roll(x, w):
        cs = np.cumsum(np.nan_to_num(x)); return (cs - np.r_[np.zeros(w), cs[:-w]]) / w
    F = np.column_stack([loi - _lag(t, loi, 1), loi - _lag(t, loi, 4), loi - _lag(t, loi, 24), loi - _lag(t, loi, 72),
                         loi - np.log(np.where(m30 > 0, m30, np.nan)), lta, ltp, lls, lls - _lag(t, lls, 24),
                         ltk, roll(ltk, 4), roll(ltk, 24), ltp - lls]).astype(np.float32)
    F[:720, 4] = np.nan
    _C[sym] = (t, F); return _C[sym]
def at(syms, H):
    out = np.full((len(H), len(NAMES)), np.nan, np.float32)
    syms = np.asarray(syms); H = np.asarray(H, dtype=np.int64)
    for s in np.unique(syms):
        cd = coin(str(s))
        if cd is None: continue
        t, F = cd; m = np.where(syms == s)[0]
        j = np.searchsorted(t, H[m]); j = np.minimum(j, len(t) - 1); ok = t[j] == H[m]
        out[m[ok]] = F[j[ok]]
    return out
