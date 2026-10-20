import time, threading
from common import V, load
V.BT_TRADES_FILE = "/home/user/vp-poc-screener/vp_bt_trades.json"
import os; os.utime(V.BT_TRADES_FILE, None)
CACHE = {}
def rng(sym, tf, a, b):
    s = sym.replace("_", "")
    if s not in CACHE: CACHE[s] = load(s)
    h1 = CACHE[s] or []
    bars = h1 if tf == "1h" else V._oc_agg(h1, {"4h": 4, "1d": 24}[tf])
    return [c for c in bars if a <= c["time"] <= b]
V.get_candles_range = rng
threading.Thread(target=lambda: V.app.run(port=5097, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium"); pg = b.new_page(viewport={"width": 400, "height": 900})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:5097/"); pg.wait_for_timeout(2500)
    pg.click('.tab[data-tab="prv"]'); pg.wait_for_timeout(2500)
    pg.click('#prvPanel >> text=📜 Сделки бэктеста'); pg.wait_for_timeout(2000)
    rows = pg.locator('#btBox_prv div[onclick^="btOpen"]')
    for k in range(rows.count()):
        if "LTC" in rows.nth(k).inner_text(): rows.nth(k).click(); break
    else: rows.nth(3).click()
    pg.wait_for_timeout(2500); pg.screenshot(path="ui_prv_chart_slim.png"); print("errors", errs); b.close()
