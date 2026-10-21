"""v0.99.676: a late scan (after a restart): P/R / Neuro signals whose limit the price already reached this hour stay
virtual (rt / late), the ones whose limit is still ahead are watched as usual; the cascade opens no real trade late"""
import types, time
from common import V as vp
T0 = 1790172000
vp.time = types.SimpleNamespace(**{k: getattr(time, k) for k in ("sleep", "strftime", "gmtime", "localtime", "monotonic", "perf_counter")}, time=lambda: T0 + 1800)
CAND = {"IO_USDT": [{"time": T0, "open": 0.15, "high": 0.151, "low": 0.1368, "close": 0.149}]}
vp.get_candles_range = lambda sym, tf, a, b: CAND.get(sym, [])
vp.binance_klines = lambda sym, tf, a, b: []
for f in ("prx_save", "nx_save", "send_telegram", "notify_trade_result"): setattr(vp, f, lambda *a, **k: None)
m = {"rule": {"stop_atr": 3.0, "take_r": 1.5, "hold_bars": 48, "hard_atr": 6.0, "stop_close": True, "entry_lim_atr": 0.3, "entry_wait": 3}}
vp._PRX["trades"] = []
c = {"side": 1, "symbol": "IO_USDT", "tf": 1, "atr": 0.004, "px": 0.15, "score": 1.2}
vp.prx_open(m, c, T0, 0.15, late=True)            # lv = 0.1488 — the hour's low 0.1368 already below it
t = vp._PRX["trades"][-1]; assert t.get("late") and t.get("rt"), t
c2 = dict(c, symbol="ETH_USDT")                   # no candles: the limit still ahead
vp.prx_open(m, c2, T0, 0.15, late=True); t2 = vp._PRX["trades"][-1]; assert not t2.get("late") and not t2.get("rt"), t2
vp.prx_open(m, dict(c, symbol="IO_USDT", side=-1), T0, 0.15, late=False); t3 = vp._PRX["trades"][-1]; assert not t3.get("late"), t3
print("P/R: touched -> virtual only, ahead -> watched, on time -> as before: ok")
mn = {"rule": {"stop_atr": 1.0, "take_r": 3.0, "hold_h": 12, "entry_lim_atr": 0.3, "entry_wait": 3}}
vp._NX["trades"] = []
vp.nx_open(mn, dict(c, score=0.9), T0, 0.15, late=True); tn = vp._NX["trades"][-1]; assert tn.get("late") and tn.get("rt"), tn
print("Neuro: touched -> virtual only: ok")
