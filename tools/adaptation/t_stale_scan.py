"""v0.99.675: a scan older than an hour (before a restart) is labelled as such on the P/R tab"""
import time, threading
from common import V
V.prx_model()
V._PRX["scan"] = {"t": int(time.time()) - 5000, "hour": int(time.time()) // 3600 * 3600 - 3600, "coins": 120, "events": 26, "signals": 0, "opened": 0, "btc_skip": 0}
threading.Thread(target=lambda: V.app.run(port=5101, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium"); pg = b.new_page(viewport={"width": 420, "height": 900})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:5101/"); pg.wait_for_timeout(2500); pg.click('.tab[data-tab="prv"]'); pg.wait_for_timeout(3000)
    t = pg.locator("body").inner_text()
    print("stale note:", "скан до перезапуска" in t, "| model shown:", "211 монет Binance" in t, "| errors", errs); b.close()
