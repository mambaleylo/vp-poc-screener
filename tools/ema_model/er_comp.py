import numpy as np, pandas as pd
from mk import ts
from common import D
from er_wf import replay
LAB = "F_0.5_2.0_1"
d = pd.read_parquet(f"{D}/er_all.parquet", columns=["sym", "t", "tf_s", "n_i", "side", LAB, LAB + "_h"])
d["pen"] = pd.read_parquet(f"{D}/er_pen.parquet").pen.values
S = np.load(f"{D}/er_sc_{LAB}.npz"); T = d.t.values
rows = []
for Y in (2022, 2023, 2024, 2025):
    sc = S[str(Y)]
    ref = (T >= ts(Y - 1)) & (T < ts(Y) - 21 * 86400)
    thr = float(np.quantile(sc[ref], 0.97))
    te = (T >= ts(Y)) & (T < (ts(Y + 1) if Y < 2025 else ts(2027))) & (d.pen.values >= 0.1) & (sc >= thr)
    rows.append(d[te].assign(Y=Y))
x = pd.concat(rows)
x["win"] = x[LAB] > 0
print(x.groupby("tf_s")[LAB].agg(["count", "mean"]).round(3))
print(x.groupby(["tf_s", "n_i"])[LAB].agg(["count", "mean"]).round(3).to_string())
print(x.groupby("side")[LAB].agg(["count", "mean"]).round(3))
print(x.groupby(["Y", "side"])[LAB].agg(["count", "mean"]).round(3).unstack())
