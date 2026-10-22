"""v0.99.683 — ⚡ one trade at a time on a fake exchange: armed limits stay in the bot until the price comes within
0.5 ATR, one order on Gate at a time, the fill drops the rest, no new order while the trade is open, the take -> WIN, the
next limit after that; the risk scaled down to the free margin; a virtual fill of a never-placed limit -> MISSED"""
import sys, time
from common import V
exec(open("t_dlm_bot.py").read().split("# (4) the real path on a fake exchange")[1].split("V.AUTOTRADE_DRY_RUN = False")[0])
V.AUTOTRADE_DRY_RUN = False; V.AUTOTRADE_ENABLED_DLM = True; V.DLM_SINGLE = True; V.dlm_save = lambda: None
calls = []
def crbp(direction, entry, sl, cap, mmr, equity, risk_pct=None, **k):
    calls.append(risk_pct); return (80.0 * risk_pct / 50.0, 40, None)
V.compute_risk_based_position = crbp
V.get_futures_wallet_balance = lambda: 50.0
PX = {}
V.get_tickers = lambda: [{"contract": c, "last": str(p)} for c, p in PX.items()]
V._DLM.update({"orders": [], "trades": []})
now = time.time(); tb = int(now // 900 * 900)
mk = lambda sym, side, lv, sc: {"id": f"dlm_{sym}_{side}_{tb}", "symbol": sym, "side": side, "lv": lv, "atr": 0.01, "score": sc, "t0": tb, "until": tb + 3600, "px": lv + side * 0.02, "status": "OPEN", "real": None}
a, b, c = mk("AAA_USDT", 1, 1.0, 0.1), mk("BBB_USDT", 1, 2.0, 0.2), mk("CCC_USDT", -1, 3.0, 0.3)
V._DLM["orders"] += [a, b, c]
ok = True
PX.update({"AAA_USDT": 1.02, "BBB_USDT": 2.02, "CCC_USDT": 2.98})   # all 2 ATR away
V.dlm_single_arm(); s1 = not any(o.get("real") for o in (a, b, c))
PX["BBB_USDT"] = 2.004; PX["AAA_USDT"] = 1.004                         # two come within 0.5 ATR: the nearer one goes (equal: the higher score)
V.dlm_single_arm(); placed = [o["symbol"] for o in (a, b, c) if (o.get("real") or {}).get("id")]
s2 = placed == ["BBB_USDT"] and calls[-1] < 50
V.dlm_single_arm(); s3 = sum(1 for o in (a, b, c) if (o.get("real") or {}).get("id")) == 1   # still one on the exchange
X_.fill(b["real"]["id"]); V.dlm_real_tick()
tb_ = next(t for t in V._DLM["trades"] if t["symbol"] == "BBB_USDT")
s4 = a["status"] == "SKIP" and c["status"] == "SKIP" and tb_["status"] == "OPEN"
d = mk("DDD_USDT", 1, 4.0, 0.5); d["id"] += "x"; V._DLM["orders"].append(d); PX["DDD_USDT"] = 4.001
V.dlm_single_arm(); s5 = not d.get("real")                               # a trade is open: nothing new
X_.fill(tb_["real"]["tp_id"]); V.dlm_real_tick(); V.dlm_real_tick()
s6 = tb_["result"] == "WIN"
V.dlm_single_arm(); s7 = bool((d.get("real") or {}).get("id"))           # free again: the next one goes
# the virtual settle in the single real mode: a touched limit that never went to Gate is no trade
e = mk("EEE_USDT", 1, 5.0, 0.4); e["id"] += "e"; V._DLM["orders"] = [e]; V._DLM["trades"] = []
V.get_candles_range = lambda sym, tf, a_, z_: [{"time": tb, "open": 5.05, "high": 5.06, "low": 4.99, "close": 5.0}]
V.dlm_settle(tb + 930); s8 = e["status"] == "MISSED" and not V._DLM["trades"]
print(f"far: none placed {s1} · near: the nearer one, risk scaled to the free margin {s2} ({calls[-1]}%) · still one {s3} · fill drops the rest {s4} · "
      f"no new while open {s5} · take -> WIN {s6} · the next after {s7} · virtual MISSED {s8}")
ok = all((s1, s2, s3, s4, s5, s6, s7, s8))
print("ALL OK" if ok else "FAILED"); sys.exit(0 if ok else 1)
