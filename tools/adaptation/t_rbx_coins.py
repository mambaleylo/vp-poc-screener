"""v0.99.672: the breakout scan walks the research's 127 coins (RBX_COINS), not Gate's live top"""
import types
from common import V as vp
seen = []
vp._own_top_syms = lambda n=None: ["HYPE_USDT", "TRUMP_USDT", "BTC_USDT"]
vp.rbx_bars = lambda sym, chart, now, start=None: (seen.append(sym), [])[1]
for f in ("rbx_save", "send_telegram"): setattr(vp, f, lambda *a, **k: None)
vp.get_tickers = lambda *a, **k: []
vp.rbx_scan_once("1d")
assert len(vp.RBX_COINS) == 127 and "HYPE_USDT" not in seen and "TRUMP_USDT" not in seen and "BTC_USDT" in seen and "PEPE_USDT" in seen, (len(vp.RBX_COINS), seen[:5])
print("scanned", len(set(seen)), "coins; HYPE / TRUMP not scanned: ok")
