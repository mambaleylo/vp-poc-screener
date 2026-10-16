import numpy as np, pandas as pd
from mk import ts
from common import D
from er_build import STOPS, TAKES, HOLDS
d = pd.read_parquet(f"{D}/er_all.parquet")
per = np.where(d.t < ts(2022), "≤21", np.where(d.t < ts(2023), "22", np.where(d.t < ts(2024), "23", np.where(d.t < ts(2025), "24", "25+"))))
d["per"] = per
print(d.groupby(["tf_s", "side"]).size().unstack())
labs = [f"E_{a}_{R}_{h}" for a in STOPS for R in TAKES for h in HOLDS]
res = []
for c in labs:
    m = d.groupby("per")[c].mean()
    res.append((c, *[round(m.get(p, np.nan), 3) for p in ["≤21", "22", "23", "24", "25+"]]))
r = pd.DataFrame(res, columns=["rule", "≤21", "22", "23", "24", "25+"])
r["min"] = r[["22", "23", "24", "25+"]].min(axis=1)
print(r.sort_values("min", ascending=False).head(12).to_string())
# by tf x side for one middle rule
for lab in ("E_1.0_2.0_7", "E_2.0_2.0_21", "E_0.5_2.0_2"):
    print("\n", lab)
    print(d.groupby(["tf_s", "side", "per"])[lab].mean().unstack().round(3).to_string())
