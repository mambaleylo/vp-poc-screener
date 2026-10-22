"""v0.99.681 — the Binance source of the research modules' candles: a mocked fapi/v1/klines over the local Binance data"""
import sys, numpy as np
from common import V, D
import s15_engine as E
DATA = {}
def local(bsym, interval):
    if (bsym, interval) not in DATA:
        if interval == "15m":
            T, O, H, L, C, Vv = E.load15(bsym)
        else:
            a = np.loadtxt(f"{D}/data/1h/{bsym}.csv", delimiter=",", ndmin=2)
            T, O, H, L, C, Vv = a[:, 0].astype(np.int64), a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5]
            if interval == "1d":
                g = T // 86400; st = np.flatnonzero(np.r_[True, g[1:] != g[:-1]]); en = np.r_[st[1:], len(T)]
                T, O, H, L, C, Vv = g[st] * 86400, O[st], np.maximum.reduceat(H, st), np.minimum.reduceat(L, st), C[en - 1], np.add.reduceat(Vv, st)
        DATA[(bsym, interval)] = (T, O, H, L, C, Vv)
    return DATA[(bsym, interval)]
CALLS = []
class R:
    def __init__(s, code, js): s.status_code, s._js = code, js
    def json(s): return s._js
FAIL = {"on": False}
def fake_get(url, params=None, timeout=None):
    if FAIL["on"]: raise ConnectionError("down")
    bsym, iv = params["symbol"], params["interval"]
    try: T, O, H, L, C, Vv = local(bsym, iv)
    except Exception: return R(400, {"code": -1121})
    s_, e_ = params["startTime"] // 1000, params["endTime"] // 1000
    idx = np.flatnonzero((T >= s_) & (T <= e_))[:params["limit"]]
    CALLS.append((bsym, iv, params["limit"], len(idx)))
    return R(200, [[int(T[i]) * 1000, str(O[i]), str(H[i]), str(L[i]), str(C[i]), "0", 0, str(Vv[i])] for i in idx])
V.requests.get = fake_get
V._bnc_state["next"] = 0
ok = True
T, O, H, L, C, Vv = local("SOLUSDT", "1h")
now = int(T[-200]) + 3600 + 30          # just after a bar closed
b = V._zm_closed("SOL_USDT", "1h", 3600, 1000, now)
k = np.searchsorted(T, now - 3600, side="right")
same = len(b) == 1000 and b[-1]["time"] == T[k - 1] and abs(b[0]["close"] - C[k - 1000]) < 1e-9 and b[-1].get("bn")
n0 = len(CALLS)
b2 = V._zm_closed("SOL_USDT", "1h", 3600, 1000, now + 3 * 3600)
inc = len(CALLS) - n0 == 1 and b2[-1]["time"] == T[k + 2] and len(b2) == 1000
past = V.bn_closed("SOL_USDT", "1h", 3600, 100, now - 10 * 3600)
past_ok = past is not None and past[-1]["time"] == T[k - 11] and len(past) == 100
too_old = V.bn_closed("SOL_USDT", "1h", 3600, 1000, now - 900 * 3600)
print(f"(1) first load {same} · top-up with 1 call {inc} · an earlier moment {past_ok} · too early -> None {too_old is None}")
ok &= bool(same) and inc and past_ok and too_old is None
# the 1000-coins
Tp = local("1000PEPEUSDT", "1h")[0]; Cp = local("1000PEPEUSDT", "1h")[4]
nowp = int(Tp[-50]) + 3630
bp = V._zm_closed("PEPE_USDT", "1h", 3600, 500, nowp)
kp = np.searchsorted(Tp, nowp - 3600, side="right")
scaled = bp and abs(bp[-1]["close"] - Cp[kp - 1] / 1000) < 1e-12
print("(2) PEPE_USDT -> 1000PEPEUSDT / 1000:", bool(scaled)); ok &= bool(scaled)
# 15m and 1d for the ⚡ module
T15 = local("ARBUSDT", "15m")[0]; now15 = int(T15[-10]) + 930
b15 = V._dlm_closed("ARB_USDT", "15m", 900, 3000, now15); d1 = V._dlm_closed("ARB_USDT", "1d", 86400, 400, now15)
print("(3) 15m", len(b15), b15[-1]["time"] == now15 - 930, "· 1d", len(d1)); ok &= len(b15) == 3000 and b15[-1]["time"] == now15 - 930 and len(d1) > 300
# Binance down -> Gate
FAIL["on"] = True
V._BNC.clear()
V.get_candles_range = lambda sym, tf, a, z: [{"time": t, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1} for t in range((a // 3600) * 3600, z, 3600)]
g = V._zm_closed("SOL_USDT", "1h", 3600, 10, now)
print("(4) Binance down -> Gate's candles:", len(g) == 10 and not g[-1].get("bn")); ok &= len(g) == 10 and not g[-1].get("bn")
FAIL["on"] = False
# a coin Binance does not have -> Gate, remembered for 6 h
g2 = V._zm_closed("NOSUCH_USDT", "1h", 3600, 10, now); g3 = V._zm_closed("NOSUCH_USDT", "1h", 3600, 10, now)
miss = V._BNC.get(("NOSUCH_USDT", "1h"), {}).get("miss", 0) > now
print("(5) unknown on Binance -> Gate, remembered:", len(g2) == 10 and miss); ok &= len(g2) == 10 and miss
print("calls", len(CALLS)); print("ALL OK" if ok else "FAILED"); sys.exit(0 if ok else 1)
