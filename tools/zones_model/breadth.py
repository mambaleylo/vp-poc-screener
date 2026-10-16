"""market-wide daily series from all coins' daily closes: share above EMA50 / EMA200, median 7d / 30d return,
BTC 30d minus the median alt 30d. Value for day D uses closes up to D (known after D's close)."""
import numpy as np, pandas as pd, pickle
from common import D, V, load, coins
closes = {}
for sym in coins():
    cs = load(sym)
    d1 = V._oc_agg(cs, 24)
    closes[sym] = pd.Series([c["close"] for c in d1], index=[c["time"] for c in d1])
P = pd.DataFrame(closes).sort_index()
e50 = P.ewm(span=50, adjust=False, min_periods=50).mean()
e200 = P.ewm(span=200, adjust=False, min_periods=200).mean()
valid50 = P.notna() & e50.notna()
br = pd.DataFrame(index=P.index)
br["above50"] = ((P > e50) & valid50).sum(1) / valid50.sum(1).replace(0, np.nan)
v200 = P.notna() & e200.notna()
br["above200"] = ((P > e200) & v200).sum(1) / v200.sum(1).replace(0, np.nan)
r7 = P.pct_change(7, fill_method=None) * 100
r30 = P.pct_change(30, fill_method=None) * 100
br["med7"] = r7.drop(columns=["BTCUSDT"]).median(1)
br["med30"] = r30.drop(columns=["BTCUSDT"]).median(1)
br["btc_vs_alt30"] = r30["BTCUSDT"] - br["med30"]
br["disp7"] = r7.drop(columns=["BTCUSDT"]).std(1)
br["n"] = P.notna().sum(1)
br = br[br.n >= 10]
br.to_pickle(f"{D}/breadth.pkl")
print(br.tail(3)); print(br.describe().round(2))
