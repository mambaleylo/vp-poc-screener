"""one table: features (stage A x + stage B f) + labels (ladder grid, confirmation entries)"""
import pickle, glob, os, numpy as np, pandas as pd
from common import D, V
from build2 import BUFS, TPS
names = list(V._OWN_FEATS) + list(V._OC_CTX_FEATS)
parts = []
for fn in sorted(glob.glob(f"{D}/ds2/*.pkl")):
    sym = os.path.basename(fn)[:-4]
    rows2 = pickle.load(open(fn, "rb"))
    rows = pickle.load(open(f"{D}/ds/{sym}.pkl", "rb"))
    labs3 = pickle.load(open(f"{D}/ds3/{sym}.pkl", "rb"))
    key3 = {(r["i"], r["side"], round(r["lo"], 10), round(r["hi"], 10)): l for r, l in zip(rows, labs3)}
    recs = []
    for r in rows2:
        d = {"sym": sym, "t": r["t"], "i": r["i"], "side_s": r["side"], "lo": r["lo"], "hi": r["hi"], "datr_raw": r["datr"]}
        d.update(zip(names, r["x"]))
        d.update(r["f"])
        for (bk, bv), lab_row in zip([(b, t) for b in BUFS for t in TPS], r["lab"]):
            (bk_, bv_), (tk, tv) = bk, bv
            nm = f"L_{bk_}{bv_}_{tk}{tv}"
            d[nm] = np.nan if lab_row is None else lab_row[0]
            d[nm + "_h"] = np.nan if lab_row is None else lab_row[1]
        l3 = key3.get((r["i"], r["side"], round(r["lo"], 10), round(r["hi"], 10)))
        for mi, mn in enumerate(["rej7", "rejt7", "sw7", "rej14"]):
            lab = l3[mi] if l3 else None
            for ki, k in enumerate([1.0, 1.5, 2.0, 3.0, 5.0]):
                d[f"C_{mn}_{k}"] = np.nan if lab is None else lab["out"][ki][0]
                d[f"C_{mn}_{k}_h"] = np.nan if lab is None else lab["out"][ki][1]
            d[f"C_{mn}_risk"] = np.nan if lab is None else lab["risk_pct"]
            d[f"C_{mn}_j"] = np.nan if lab is None else lab["j"]
        recs.append(d)
    p = pd.DataFrame(recs)
    for c in p.columns:
        if p[c].dtype == np.float64:
            p[c] = p[c].astype(np.float32)
    parts.append(p)
    del recs
df = pd.concat(parts, ignore_index=True)
df.to_parquet(f"{D}/all.parquet")
print(df.shape, df.memory_usage().sum() / 1e9, "GB")
