import time, threading, os
from common import V, load
os.utime(V.BT_TRADES_FILE, None)
CACHE = {}
def rng(sym, tf, a, b):
    if tf == "1h" and a < time.time() - 9800 * 3600: return []
    s = sym.replace("_", "")
    if s not in CACHE: CACHE[s] = load(s) or []
    h1 = CACHE[s]
    bars = h1 if tf == "1h" else V._oc_agg(h1, {"4h": 4, "1d": 24}[tf])
    return [c for c in bars if a <= c["time"] <= b]
V.get_candles_range = rng
V.cas_model()
threading.Thread(target=lambda: V.app.run(port=5098, use_reloader=False), daemon=True).start()
time.sleep(2)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium"); pg = b.new_page(viewport={"width": 400, "height": 900})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:5098/"); pg.wait_for_timeout(2500)
    for tab, box in (("cas", "btBox_cas"),):
        pg.click(f'.tab[data-tab="{tab}"]'); pg.wait_for_timeout(2500)
        pg.screenshot(path=f"ui_part_{tab}.png", full_page=True)
        pg.click(f'#{tab}Panel >> text=📜 Сделки бэктеста'); pg.wait_for_timeout(2000)
        for _ in range(3):
            b2 = pg.locator(f'#{box} button:has-text("ещё")')
            if b2.count(): b2.first.click(); pg.wait_for_timeout(500)
        rows = pg.locator(f'#{box} div[onclick^="btOpen"]')
        for k in range(rows.count()):
            tx = rows.nth(k).inner_text()
            if ".25 " in tx and "1000" not in tx: rows.nth(k).click(); break
        pg.wait_for_timeout(3000)
        pg.screenshot(path=f"ui_part_{tab}_chart.png")
        print(tab, "params", pg.locator("#vgiModalParams").inner_text()[:160].replace("\n", " "))
        pg.click("#vgiCloseBtn"); pg.wait_for_timeout(500)
    print("errors", errs)
    b.close()
