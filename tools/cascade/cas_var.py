import os, sys, subprocess
TAG = sys.argv[1]
os.environ["CAS_SEL"] = f"cas_sel_{TAG}.npz"
from cas_part import trades
from wr_eval import stats
from mk import ts
import numpy as np
for q, tg, nm in ((0.995, 0.45, "бот"), (0.98, 0.50, "проверка")):
    tr = trades(q); r = np.array([x[2] for x in tr if x[0] >= ts(2022)]); t = np.array([x[0] for x in tr if x[0] >= ts(2022)])
    yrs = " ".join(f"{r[(t >= ts(y)) & (t < ts(y + 1))].mean():+.2f}" for y in range(2022, 2027))
    stats(f"{TAG:6s} {nm} [{yrs}]", [x[:5] for x in tr], ts(2022), tg)
