"""The market's breadth hour by hour (the user's drawdown round: "признаки ширины рынка" for ⚡ — the deep drawdowns are the
whole market running one way while ⚡'s clustered limits catch it): over the 210 base coins of the ⚡ lab (feat_coins.json,
the lab-store's 1h candles), at the close of each hour: the mean 24 h / 72 h return, the share of coins up > 5% / down > 5%
in 24 h, the cross-section's spread of the 24 h returns, the share above their 7-day average. Only closed hours: the value at
the hour h uses the candles up to h's close. -> <LABSTORE>/wf/breadth.npz (T = the hour's open, the arrays)"""
import os, json, gzip, numpy as np
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
C = json.load(open(f"{ST}/feat_coins.json"))["base"]
T0, T1 = 1609459200, 1793491200   # 2021-01-01 .. 2026-11-01
H = np.arange(T0, T1, 3600, dtype=np.int64); n = len(H)
L = np.full((len(C), n), np.nan, np.float32)
for k, c in enumerate(C):
    fn = f"{ST}/data/1h/{c}.csv.gz"
    if not os.path.exists(fn): continue
    a = np.loadtxt(gzip.open(fn, "rt"), delimiter=",", usecols=(0, 4), ndmin=2)
    t = a[:, 0].astype(np.int64); m = (t >= T0) & (t < T1) & (a[:, 1] > 0)
    L[k, (t[m] - T0) // 3600] = np.log(a[m, 1])
    if k % 50 == 0: print(k, c, flush=True)
def ret(lag):
    r = np.full_like(L, np.nan); r[:, lag:] = L[:, lag:] - L[:, :-lag]; return r
r24, r72 = ret(24), ret(72)
with np.errstate(all="ignore"):
    cs = np.nancumsum(np.nan_to_num(L), axis=1); cnt = np.cumsum(np.isfinite(L), axis=1)
    s168 = (cs[:, 168:] - cs[:, :-168]) / np.maximum(cnt[:, 168:] - cnt[:, :-168], 1)
    above = np.full_like(L, np.nan); above[:, 168:] = (L[:, 168:] > s168).astype(np.float32); above[~np.isfinite(L)] = np.nan
    out = dict(T=H, r24=np.nanmean(r24, 0), r72=np.nanmean(r72, 0), up5=np.nanmean(r24 > np.log(1.05), 0, where=np.isfinite(r24)),
               dn5=np.nanmean(r24 < np.log(0.95), 0, where=np.isfinite(r24)), disp=np.nanstd(r24, 0), above=np.nanmean(above, 0),
               n=np.isfinite(r24).sum(0))
np.savez_compressed(f"{ST}/wf/breadth.npz", **{k: np.nan_to_num(v.astype(np.float64)) if k not in ("T", "n") else v for k, v in out.items()})
i = np.searchsorted(H, 1696896000)   # 2023-10-10 for a look
print("coins with data (median)", int(np.median(out["n"][out["n"] > 0])), "| a sample:", {k: round(float(v[i]), 4) for k, v in out.items() if k not in ("T",)})
print("breadth done", flush=True)
