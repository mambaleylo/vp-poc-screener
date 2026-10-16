import pickle, glob, os, numpy as np, pandas as pd
from common import D
from build4 import GRID
d = pd.read_parquet(f"{D}/all.parquet")
cols = {f"G_{b}_{tk}{tv}": [] for b, (tk, tv) in GRID}
hcols = {f"G_{b}_{tk}{tv}_h": [] for b, (tk, tv) in GRID}
order = []
for sym in d.sym.unique():
    labs = pickle.load(open(f"{D}/ds4/{sym}.pkl", "rb"))
    for lab in labs:
        for (b, (tk, tv)), l in zip(GRID, lab):
            cols[f"G_{b}_{tk}{tv}"].append(np.nan if l is None else l[0])
            hcols[f"G_{b}_{tk}{tv}_h"].append(np.nan if l is None else l[1])
# the parquet was written coin by coin in the same order as ds2 rows
assert len(next(iter(cols.values()))) == len(d), (len(next(iter(cols.values()))), len(d))
syms_order = list(dict.fromkeys(d.sym.values))
for k, v in {**cols, **hcols}.items():
    d[k] = np.array(v, dtype=np.float32)
d.to_parquet(f"{D}/all.parquet")
print(d.shape)
