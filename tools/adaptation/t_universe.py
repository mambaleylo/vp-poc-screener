"""v0.99.673: every model module scans only the coins it was tested on, in Gate's live volume order; stock perps
(MSTR / CRCL) and untested coins are never scanned"""
from common import V as vp
TICK = [{"contract": c, "volume_24h_quote": str(v)} for c, v in
        (("BTC_USDT", 9e9), ("MSTR_USDT", 8e9), ("CRCL_USDT", 7e9), ("ETH_USDT", 6e9), ("HYPE_USDT", 5e9), ("ICNT_USDT", 4e9), ("PEPE_USDT", 3e9), ("DOOD_USDT", 2e9))]
vp.get_tickers = lambda *a, **k: TICK
assert len(vp.RESEARCH_COINS_127) == 127 and len(vp.RESEARCH_COINS_211) == 211 and vp.RBX_COINS == vp.RESEARCH_COINS_127
a = vp._research_syms(vp.RESEARCH_COINS_127); b = vp._research_syms(vp.RESEARCH_COINS_211, 300)
assert a == ["BTC_USDT", "ETH_USDT", "PEPE_USDT"], a
assert b == ["BTC_USDT", "ETH_USDT", "HYPE_USDT", "PEPE_USDT"], b
print("127:", a, "| 211:", b, "| MSTR / CRCL / ICNT / DOOD skipped: ok")
