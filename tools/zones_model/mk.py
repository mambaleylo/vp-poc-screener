import numpy as np, pandas as pd, datetime as dt
from common import D, V
def ts(y, m=1):
    return int(dt.datetime(y, m, 1, tzinfo=dt.timezone.utc).timestamp())
HOLD_S = 14 * 86400
_DF = {}
def df(labels=None):
    if "df" not in _DF:
        if labels is None:
            _DF["df"] = pd.read_parquet(f"{D}/all.parquet")
        else:
            import pyarrow.parquet as pq
            names = pq.ParquetFile(f"{D}/all.parquet").schema.names
            keep = [c for c in names if c.split("_")[0] not in ("L", "C", "G")] + [c for c in labels if c in names]
            _DF["df"] = pd.read_parquet(f"{D}/all.parquet", columns=keep)
    return _DF["df"]
XA = list(V._OWN_FEATS) + list(V._OC_CTX_FEATS)
def feats(d):
    skip = set(XA) | {"sym", "t", "i", "side_s", "lo", "hi", "datr_raw"}
    fb = [c for c in d.columns if c not in skip and c.split("_")[0] not in ("L", "C", "G", "m", "ms")]
    return XA + fb

def replay(d, score, thr, lab, busy_h=None, hcol=None):
    """one active zone per coin & side; returns trades DataFrame (t, sym, r)"""
    m = score >= thr
    sub = d.loc[m, ["t", "sym", "side_s"]].copy()
    sub["sc"] = score[m]
    sub["r"] = d.loc[m, lab].values
    sub["bh"] = busy_h[m] if busy_h is not None else np.nan
    sub["h"] = d.loc[m, hcol].values if hcol else np.nan
    sub = sub.sort_values(["t", "sc"], ascending=[True, False])
    busy = {}
    out = []
    for t, sym, side, sc, r, bh, h in sub.itertuples(index=False):
        k = (sym, side)
        if busy.get(k, 0) > t:
            continue
        b = t + (bh * 3600 if bh == bh else HOLD_S)
        busy[k] = b
        out.append((t, sym, r, h))
    return pd.DataFrame(out, columns=["t", "sym", "r", "h"])

def st(tr, t0, t1):
    x = tr[(tr.t >= t0) & (tr.t < t1)]
    f = x.r.dropna()
    wk = (t1 - t0) / (7 * 86400)
    if not len(f):
        return {"n": 0}
    return {"n": len(f), "avg": round(f.mean(), 3), "wr": round((f > 0).mean() * 100, 1), "sum": round(f.sum(), 1), "wk": round(len(f) / wk, 2)}

BR_COLS = ["above50", "above200", "med7", "med30", "btc_vs_alt30", "disp7"]
def add_breadth(d):
    br = pd.read_pickle(f"{D}/breadth.pkl")
    bt = br.index.values + 86400   # known after the day closed
    k = np.searchsorted(bt, d.t.values, side="right") - 1
    ok = k >= 0
    sg = np.where(d.side_s.values == "long", 1.0, -1.0)
    for c in BR_COLS:
        v = np.full(len(d), np.nan, dtype=np.float32)
        v[ok] = br[c].values[k[ok]]
        d["m_" + c] = v
        d["ms_" + c] = (v - (0.5 if c.startswith("above") else 0.0)) * sg
    return d
