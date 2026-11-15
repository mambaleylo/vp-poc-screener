"""v0.99.796 — the bugs found in the bundle (the user: "Поищи баги в связке"): (1) P/R's live limit counted from the price at the
scan, the research's from the entry bar's open (ATOM 11.11: the research's limit reached, +0.73R; the live one never) -> now from
the open of Binance's forming hour, the scan's price only when Binance does not answer; (2) the real fills of a closed ⚡ trade
fetched only while another ⚡ limit / trade stood on Binance (H_USDT 10.11: none ever) -> fetched always; (3) «разгон»'s $ counted
before the fills came and, for a 1000-coin, from the fills in the bot's prices x Binance's quantity (1000x off) -> after the fills
(or 15 min), in Binance's prices"""
import time
from common import V
ok = True
def chk(nm, c):
    global ok
    print(("OK  " if c else "FAIL") + " " + nm); ok &= bool(c)
V.log_error = lambda m: None; V.send_telegram = lambda *a, **k: None; V.save_settings = lambda: None; V.dlm_save = lambda: None; V.prx_save = lambda: None
# (1) P/R
h = int(time.time()) // 3600 * 3600
m = {"rule": {"stop_atr": 3.0, "take_r": 1.5, "hold_bars": 48, "entry_lim_atr": 0.3, "entry_wait": 3, "stop_close": True, "hard_atr": 6.0}}
c = {"side": -1, "symbol": "ATOM_USDT", "tf": 1, "atr": 0.01537, "px": 1.431, "score": 0.708}
V.bn_routed = lambda mode: True; V.AUTOTRADE_ENABLED_PRV = False; V.TELEGRAM_ALERTS_PRV = False
V.binance_klines = lambda sym, iv, a, b: [{"time": h, "open": 1.428, "high": 1.433, "low": 1.427, "close": 1.431, "forming": True}]
V._PRX["trades"] = []; V.prx_open(m, c, h, live_px=1.431)
lv = V._PRX["trades"][-1]["lv"]
chk(f"P/R: лимитка от открытия часа, как в исследовании: {lv:.5f} = 1.428 + 0.3 ATR (было от цены скана: {1.431 + 0.3 * 0.01537:.5f})", abs(lv - (1.428 + 0.3 * 0.01537)) < 1e-9)
V.binance_klines = lambda *a: []; V._PRX["trades"] = []; V.prx_open(m, c, h, live_px=1.431)
chk("P/R: Binance не ответил — от цены скана, как раньше", abs(V._PRX["trades"][-1]["lv"] - (1.431 + 0.3 * 0.01537)) < 1e-9)
# (2) the fills fetched with nothing of ⚡ on the exchange
calls = []; V._dlm_bn_fills = lambda now=None, most=3: calls.append(1) or False
V.DLM_BINANCE = True; V.BINANCE_API_KEY = "k"; V.AUTOTRADE_DRY_RUN = False; V._ADOPT["t"] = time.time(); V._dlm_arm = lambda now: None
V._DLM.update(orders=[], trades=[{"id": "h", "symbol": "H_USDT", "side": 1, "status": "CLOSED", "real": {"ex": "binance", "bsym": "HUSDT"}, "t_out": int(time.time()) - 60}])
V.dlm_real_tick()
chk("⚡: ни лимиток, ни сделок на бирже — реальные исполнения закрытой сделки всё равно запрашиваются", calls)
# (3) the boost tally
now = int(time.time())
def trade(scl, fills, t_out):
    r = {"ex": "binance", "bsym": "1000PEPEUSDT" if scl == 1000 else "AAAUSDT", "scl": scl, "boost": 100.0, "filled": 1_000_000.0 if scl == 1000 else 1000.0}
    if fills: r.update(fills=4, e_real=0.00001, x_real=0.0000104)
    return {"id": f"b{scl}{fills}", "symbol": "PEPE_USDT" if scl == 1000 else "AAA_USDT", "side": 1, "entry": 0.00001, "exit": 0.0000104, "status": "CLOSED", "result": "WIN", "t_out": t_out, "real": r}
V._DLM["boost"] = None; V._DLM["trades"] = [trade(1000, False, now - 30)]
V.dlm_boost_settle()
chk("разгон: сделка только что закрылась, исполнений ещё нет — итог не считается", not V._DLM["trades"][0]["real"].get("boost_done"))
V._DLM["trades"][0]["real"].update(fills=4, e_real=0.00001, x_real=0.0000104)   # the bot's PEPE prices; Binance's 1000PEPE: 0.01 -> 0.0104
V.dlm_boost_settle(); p = V._DLM["trades"][0]["real"].get("boost_pnl")
want = 1_000_000 * (0.0104 - 0.010) - 0.0005 * 1_000_000 * 0.0204   # 1 000 000 x 1000PEPE at Binance's 0.0100 -> 0.0104
chk(f"разгон: монета 1000PEPE — итог ${p} (из цен Binance; по старому коду было бы ${want / 1000:.2f})", p is not None and abs(p - want) < 0.05)
V._DLM["trades"] = [trade(1, False, now - 1000)]; V.dlm_boost_settle()
chk("разгон: исполнений так и нет 15 минут — итог по плановой цене выхода", V._DLM["trades"][0]["real"].get("boost_done"))
print("t_bugs796 OK" if ok else "t_bugs796 FAIL")
