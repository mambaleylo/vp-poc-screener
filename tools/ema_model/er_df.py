import pickle, glob, os, numpy as np, pandas as pd
from common import D
from er_build import STOPS, TAKES, HOLDS
names = [f"E_{a}_{R}_{h}" for a in STOPS for R in TAKES for h in HOLDS]
parts = []
for fn in sorted(glob.glob(f"{D}/er/*.pkl")):
    sym = os.path.basename(fn)[:-4]
    rows = pickle.load(open(fn, "rb"))
    if not rows:
        continue
    p = pd.DataFrame([r["f"] for r in rows])
    p["sym"] = sym; p["t"] = [r["t"] for r in rows]; p["j"] = [r["j"] for r in rows]
    p["tf_s"] = [r["tf"] for r in rows]; p["n_i"] = [r["n"] for r in rows]; p["lv"] = [r["lv"] for r in rows]
    lab = np.array([[x[0] for x in r["lab"]] for r in rows], dtype=np.float32)
    held = np.array([[x[1] for x in r["lab"]] for r in rows], dtype=np.int16)
    for k, nm in enumerate(names):
        p[nm] = lab[:, k]
        p[nm + "_h"] = held[:, k]
    for c in p.columns:
        if p[c].dtype == np.float64:
            p[c] = p[c].astype(np.float32)
    parts.append(p)
d = pd.concat(parts, ignore_index=True)
d.to_parquet(f"{D}/er_all.parquet")
print(d.shape)
