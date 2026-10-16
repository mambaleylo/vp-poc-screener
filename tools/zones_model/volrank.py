"""daily 30d quote-volume rank of every coin among the 127 (to mimic the bot's "top N by volume" universe)"""
import numpy as np, pandas as pd
from common import D, V, load, coins
vols = {}
for sym in coins():
    cs = load(sym)
    d1 = V._oc_agg(cs, 24)
    vols[sym] = pd.Series([c["volume"] for c in d1], index=[c["time"] for c in d1])
Q = pd.DataFrame(vols).sort_index().rolling(30, min_periods=5).mean()
R = Q.rank(axis=1, ascending=False)
R.to_pickle(f"{D}/volrank.pkl")
print(R.iloc[-1].sort_values().head(10))
