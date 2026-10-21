"""v0.99.667: the bot's binance_ls_d24 on a mocked Binance 5-min long/short feed built from the research's hourly rows
(the last 5-min value of hour H at H+55 min) = mfeat.ls_d24 of the last closed hour; 1000-coins; no answer -> None"""
import numpy as np, types
from common import V as vp
import mfeat
t, F = mfeat.coin("SOLUSDT"); raw = np.genfromtxt("data/metrics/SOLUSDT.csv", delimiter=",", skip_header=1)
LS = dict(zip(raw[:, 0].astype(int), raw[:, 5]))
class Resp:
    def __init__(s, code, rows): s.status_code, s._r = code, rows
    def json(s): return s._r
def fake_get(url, params=None, timeout=None):
    if params["symbol"] != "SOLUSDT": return Resp(400, [])
    end = params["endTime"] // 1000
    rows = [{"timestamp": (h + 3300) * 1000, "longShortRatio": str(LS[h])} for h in range(end - 40 * 3600, end, 3600) if h in LS and h + 3300 <= end]
    return Resp(200, rows)
vp.requests = types.SimpleNamespace(get=fake_get)
ok = bad = 0
for k in np.random.default_rng(1).choice(np.arange(800, len(t)), 300, replace=False):
    H = int(t[k]); vp._BN_LS.clear()
    got = vp.binance_ls_d24("SOL_USDT", H + 3600); exp = F[k, mfeat.NAMES.index("ls_d24")]
    good = (got is None and exp != exp) or (got is not None and exp == exp and abs(got - exp) < 1e-5)
    ok += good; bad += not good
    if not good and bad < 5: print("mismatch", H, got, exp)
print("ls_d24 ok", ok, "bad", bad)
print("unknown coin ->", vp.binance_ls_d24("NOPE_USDT", int(t[1000]) + 3600))
