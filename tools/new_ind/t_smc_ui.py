import time, threading, json
from common import V
V.smc_model()
V._SMC["scan"] = {"t": int(time.time()), "coins": 127, "levels": 840, "armed": 2,
                  "near": [{"symbol": "SOL_USDT", "side": 1, "fam": "fvg4_bull", "pct": 92}]}
V._SMC["armed"] = [{"symbol": "SOL_USDT", "fam": "fvgd_bull", "side": 1, "lv": 150.1, "score": 0.7, "datr": 4.0, "sl": 144.1, "tp": 168.1, "hour": int(time.time()) // 3600 * 3600, "px": 152.0, "dist": -1.25}]
V._SMC["trades"] = [{"id": "x", "symbol": "DOGE_USDT", "fam": "swd_low", "side": 1, "direction": "LONG", "entry": 0.2, "sl": 0.19, "tp": 0.23, "score": 0.7,
                     "t_in": int(time.time()) - 7200, "hour": int(time.time()) // 3600 * 3600 - 7200, "until": int(time.time()) + 3600 * 70, "hold": 72, "status": "OPEN", "r": None, "real": False},
                    {"id": "y", "symbol": "ADA_USDT", "fam": "obd_bull", "side": 1, "direction": "LONG", "entry": 0.5, "sl": 0.48, "tp": 0.56, "score": 0.7,
                     "t_in": int(time.time()) - 86400 * 4, "hour": int(time.time()) // 3600 * 3600 - 86400 * 4, "until": 0, "hold": 72, "status": "CLOSED", "r": 2.9, "result": "WIN", "exit": 0.56, "t_out": int(time.time()) - 86400 * 2, "real": False}]
V.smc_save = lambda: None
threading.Thread(target=lambda: V.app.run(port=5101, use_reloader=False), daemon=True).start()
time.sleep(2)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium"); pg = b.new_page(viewport={"width": 420, "height": 900})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:5101/"); pg.wait_for_timeout(3000)
    pg.click('.tab[data-tab="smc"]'); pg.wait_for_timeout(3000)
    pg.screenshot(path="ui_smc.png", full_page=True)
    txt = pg.locator("#smcPanel").inner_text(); print(txt[:1500])
    pg.click("#smcPanel details summary >> text=Сделки бэктеста"); pg.wait_for_timeout(3000)
    print("bt list:", pg.locator("#btBox_smc").inner_text()[:400])
    pg.locator("#btBox_smc div[onclick^='btOpen']").first.click(); pg.wait_for_timeout(4000)
    pg.screenshot(path="ui_smc_chart.png")
    print("chart title:", pg.locator("#vgiModalTitle").inner_text(), "|", pg.locator("#vgiModalParams").inner_text()[:200])
    print("errors", errs)
    b.close()
