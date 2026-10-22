"""v0.99.686 — ⚡ on 210 coins: the list (no USDC), Binance mode scans all of them, Gate mode only Gate's top, a 1000-coin
found on Binance by its 1000 symbol (scaled), the switch in the settings"""
import sys, time
from common import V
res = {}
V.DLM_BINANCE = True; V.DLM_MORE_COINS = True
c = V.dlm_coins()
res["210 on Binance, no USDC"] = len(c) == 210 and "USDC_USDT" not in c and "RATS_USDT" in c and "BTC_USDT" in c
V.DLM_MORE_COINS = False; res["127 when off"] = len(V.dlm_coins()) == 127
V.DLM_MORE_COINS = True; V.DLM_BINANCE = False
V._own_top_syms = lambda n=300: ["BTC_USDT", "ETH_USDT", "HYPE_USDT", "NOTONLIST_USDT"]
res["Gate: its top only"] = V.dlm_coins() == ["BTC_USDT", "ETH_USDT", "HYPE_USDT"]
asked = []
def fake(bsym, interval, start, end, limit):
    asked.append(bsym)
    if bsym == "RATSUSDT": return False
    now = int(time.time()) // 900 * 900
    return [[(now - 900 * k) * 1000, "0.05", "0.06", "0.04", "0.055", "1", 0, "100"] for k in range(40, 0, -1)]
V._bnc_get = fake
b = V.bn_closed("RATS_USDT", "15m", 900, 30, time.time())
res["1000-coin mapped"] = bool(b) and asked[:2] == ["RATSUSDT", "1000RATSUSDT"] and abs(b[-1]["close"] - 0.000055) < 1e-12 and V.bn_map("RATS_USDT") == ("1000RATSUSDT", 1000.0)
V.apply_settings({"dlm_more_coins": False}); off = V.DLM_MORE_COINS is False and V.get_settings()["dlm_more_coins"] is False
V.apply_settings({"dlm_more_coins": True})
res["setting"] = off and V.DLM_MORE_COINS and "setDlmMoreCoins" in V.app.test_client().get("/").get_data(as_text=True)
print(" · ".join(f"{k} {v}" for k, v in res.items()))
ok = all(res.values()); print("ALL OK" if ok else "FAILED"); sys.exit(0 if ok else 1)
