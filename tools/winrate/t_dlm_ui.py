import time, threading
from common import V
V.dlm_model(); now = int(time.time()); tb = now // 900 * 900
V._DLM["scan"] = {"t": now, "bar": tb, "coins": 127, "cands": 250, "orders": 2, "near": [{"symbol": "SOL_USDT", "side": 1, "pct": 88}]}
V._DLM["orders"] = [{"id": "o1", "symbol": "SOL_USDT", "side": 1, "lv": 148.2, "atr": 1.1, "score": 0.09, "t0": tb, "until": tb + 3600, "px": 150.4, "status": "OPEN", "real": None}]
V._DLM["trades"] = [{"id": "t1", "symbol": "DOGE_USDT", "side": -1, "direction": "SHORT", "entry": 0.21, "lv": 0.21, "atr": 0.002, "sl": 0.214, "tp": 0.209, "score": 0.1, "t0": tb - 1800, "fbar": tb - 900, "t_in": now - 600, "until": tb + 3 * 3600, "status": "OPEN", "result": None, "r": None, "real": None, "rv": 1},
                    {"id": "t2", "symbol": "ADA_USDT", "side": 1, "direction": "LONG", "entry": 0.5, "lv": 0.5, "atr": 0.004, "sl": 0.492, "tp": 0.502, "score": 0.1, "t0": tb - 7200, "fbar": tb - 6300, "t_in": now - 6000, "until": 0, "status": "CLOSED", "result": "WIN", "r": 0.23, "exit": 0.502, "t_out": now - 3000, "real": None, "rv": 1}]
V.dlm_save = lambda: None
import json as _j; _BTD = _j.load(open("vp_bt_trades_v679.json")); V.bt_trades = lambda: _BTD
threading.Thread(target=lambda: V.app.run(port=5103, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium"); pg = b.new_page(viewport={"width": 420, "height": 900})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:5103/"); pg.wait_for_timeout(3000)
    pg.click('.tab[data-tab="dlm"]'); pg.wait_for_timeout(3000)
    pg.screenshot(path="ui_dlm.png", full_page=True)
    print(pg.locator("#dlmPanel").inner_text()[:900])
    pg.click("#dlmPanel details summary >> text=Сделки бэктеста"); pg.wait_for_timeout(3000)
    print("bt:", pg.locator("#btBox_dlm").inner_text()[:300])
    pg.locator("#btBox_dlm div[onclick^='btOpen']").first.click(); pg.wait_for_timeout(3000)
    print("chart:", pg.locator("#vgiModalTitle").inner_text())
    pg.keyboard.press("Escape")
    print("errors", errs); b.close()
