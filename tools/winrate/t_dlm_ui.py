"""v0.99.687 — the ⚡ 4h tab renders (a virtual order, an open and a closed trade, the backtest list and its chart) with no
page errors; the old single / ladder switches are gone"""
import time, threading, json
from common import V
V.dlm_model(); now = int(time.time()); tb = now // 14400 * 14400
V._DLM["scan"] = {"t": now, "bar": tb, "coins": 210, "cands": 300, "orders": 1, "near": [{"symbol": "SOL_USDT", "side": 1, "pct": 88}], "src": {"binance": 210, "gate": 0}}
V._DLM["orders"] = [{"id": "o1", "symbol": "SOL_USDT", "side": 1, "lv": 148.2, "atr": 3.1, "score": 0.4, "t0": tb, "bs": 14400, "until": tb + 4 * 14400, "px": 155.4, "status": "OPEN", "real": None}]
V._DLM["trades"] = [{"id": "t1", "symbol": "DOGE_USDT", "side": -1, "direction": "SHORT", "entry": 0.21, "lv": 0.21, "atr": 0.004, "sl": 0.218, "tp": 0.206, "score": 0.4, "t0": tb - 14400, "fbar": tb - 14400, "t_in": now - 6000, "until": tb + 30 * 14400, "bs": 14400, "hold": 32, "status": "OPEN", "result": None, "r": None, "real": None, "rv": 2},
                    {"id": "t2", "symbol": "ADA_USDT", "side": 1, "direction": "LONG", "entry": 0.5, "lv": 0.5, "atr": 0.01, "sl": 0.48, "tp": 0.51, "score": 0.4, "t0": tb - 8 * 14400, "fbar": tb - 7 * 14400, "t_in": now - 99000, "until": 0, "bs": 14400, "hold": 32, "status": "CLOSED", "result": "WIN", "r": 0.49, "exit": 0.51, "t_out": now - 30000, "real": None, "rv": 2},
                    {"id": "t3", "symbol": "XRP_USDT", "side": 1, "direction": "LONG", "entry": 2.0, "lv": 2.0, "atr": 0.01, "sl": 1.98, "tp": 2.005, "score": 0.1, "t0": tb - 99999, "fbar": tb - 99000, "t_in": now - 99000, "until": 0, "status": "CLOSED", "result": "WIN", "r": 0.22, "exit": 2.005, "t_out": now - 90000, "real": None, "rv": 1}]
V.dlm_save = lambda: None
_BTD = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json")); V.bt_trades = lambda: _BTD
import s20h4_engine as E
def fake_bars(symbol, ch, start, end):
    T, O, H, L, C, Vv = E.load15(symbol.replace("_USDT", "") + "USDT")
    return [{"time": int(t), "open": o, "high": h, "low": l, "close": c} for t, o, h, l, c in zip(T, O, H, L, C) if start <= t <= end]
V.bt_gate_bars = fake_bars
threading.Thread(target=lambda: V.app.run(port=5103, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium"); pg = b.new_page(viewport={"width": 420, "height": 900})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:5103/"); pg.wait_for_timeout(3000)
    html = pg.content()
    pg.click('.tab[data-tab="dlm"]'); pg.wait_for_timeout(3000)
    pg.screenshot(path="ui_dlm.png", full_page=True)
    txt = pg.locator("#dlmPanel").inner_text(); print(txt[:1500])
    pg.click("#dlmPanel details summary >> text=Сделки бэктеста"); pg.wait_for_timeout(3000)
    print("bt:", pg.locator("#btBox_dlm").inner_text()[:300])
    pg.locator("#btBox_dlm div[onclick^='btOpen']").first.click(); pg.wait_for_timeout(3000)
    pg.screenshot(path="ui_dlm_chart.png")
    print("chart:", pg.locator("#vgiModalTitle").inner_text())
    pg.keyboard.press("Escape")
    gone = "setDlmSingle" not in html and "setDlmLadder" not in html and "Лесенка" not in txt
    print("errors", errs, "· single/ladder gone", gone, "· 4h text", "4ч" in txt and "старый модуль 15м" in txt)
    b.close()
