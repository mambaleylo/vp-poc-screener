import time, threading, os
from common import V, load
os.utime(V.BT_TRADES_FILE, None)
CACHE = {}
def rng(sym, tf, a, b):
    s = sym.replace("_", "")
    if s not in CACHE: CACHE[s] = load(s) or load("1000" + s) or []
    h1 = CACHE[s]
    bars = h1 if tf == "1h" else V._oc_agg(h1, {"4h": 4, "1d": 24}[tf])
    return [c for c in bars if a <= c["time"] <= b]
V.get_candles_range = rng
V._CAS["trades"] = [{"symbol": "SOL_USDT", "side": -1, "tf": 1, "hour": 1767225600, "entry": 125.0, "px": 125.0, "sl": 128.0, "tp": 119.0,
                     "status": "CLOSED", "r": 1.95, "result": "WIN", "exit": 119.0, "t_out": 1767225600 + 20 * 3600, "real": False, "rv": 1}]
V._CAS["scan"] = {"t": int(time.time()), "hour": int(time.time()) // 3600 * 3600, "coins": 118, "events": 17, "signals": 1, "opened": 1}
V._CAS["last"] = [{"symbol": "DOGE_USDT", "side": -1, "score": 0.7, "pct": 106}, {"symbol": "ADA_USDT", "side": 1, "score": 0.5, "pct": 89}]
V.cas_model()
threading.Thread(target=lambda: V.app.run(port=5096, use_reloader=False), daemon=True).start()
time.sleep(2)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium"); pg = b.new_page(viewport={"width": 400, "height": 900})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:5096/"); pg.wait_for_timeout(2500)
    pg.click('.tab[data-tab="cas"]'); pg.wait_for_timeout(2500)
    pg.screenshot(path="ui_cas_tab.png", full_page=True)
    pg.click('#casPanel >> text=📜 Сделки бэктеста'); pg.wait_for_timeout(2000)
    rows = pg.locator('#btBox_cas div[onclick^="btOpen"]'); print("rows", rows.count())
    for k in range(rows.count()):
        tx = rows.nth(k).inner_text()
        if any(c in tx for c in ("SOL", "ETH", "LINK", "AVAX", "DOGE", "ADA")) or k >= rows.count() - 1:
            print("open", tx.replace("\n", " ")); rows.nth(k).click(); break
    pg.wait_for_timeout(3000)
    pg.screenshot(path="ui_cas_chart.png")
    print("params", pg.locator("#vgiModalParams").inner_text()[:200])
    print("errors", errs)
    b.close()
