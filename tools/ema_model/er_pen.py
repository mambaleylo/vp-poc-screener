"""how far past the EMA the touch hour went (in % of the level): a limit touched exactly may not fill"""
import os, pickle, numpy as np, pandas as pd
from common import load, D
d = pd.read_parquet(f"{D}/er_all.parquet", columns=["sym"])
pen = []
for sym in d.sym.unique():
    rows = pickle.load(open(f"{D}/er/{sym}.pkl", "rb"))
    cs = load(sym)
    for r in rows:
        c = cs[r["j"]]
        p = (c["high"] - r["lv"]) / r["lv"] * 100 if r["side"] < 0 else (r["lv"] - c["low"]) / r["lv"] * 100
        pen.append(p)
pd.DataFrame({"pen": np.array(pen, dtype=np.float32)}).to_parquet(f"{D}/er_pen.parquet")
print(len(pen), np.percentile(pen, [5, 25, 50, 75]))
