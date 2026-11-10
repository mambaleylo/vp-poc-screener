"""v0.99.764 — the bundle first (the user: "первыми идут из связки начиная с лимиток", "в настройках тоже так же"): the tab
row ⚡, P/R, SMC, EMA, (v0.99.776: 🔄 Классика,) HTF, then the rest; ⚡ opens first with its panel; the settings' groups in the same order; no page errors"""
import time, threading
from common import V
threading.Thread(target=lambda: V.app.run(port=5109, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium"); pg = b.new_page(viewport={"width": 420, "height": 900})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:5109/"); pg.wait_for_timeout(4000)
    tabs = pg.eval_on_selector_all(".tabs .tab", "els => els.map(e => e.dataset.tab)")
    assert tabs[:6] == ["dlm", "prv", "smc", "emw", "cfl", "htf"], tabs   # v0.99.776: 🔄 Классика 5th
    assert pg.eval_on_selector(".tab.active", "e => e.dataset.tab") == "dlm"
    assert pg.locator("#dlmPanel").is_visible() and not pg.locator("#prvPanel").is_visible()
    assert len(pg.locator("#dlmPanel").inner_text().strip()) > 20, pg.locator("#dlmPanel").inner_text()[:200]
    pg.screenshot(path="ui_tab_order.png")
    pg.click('.tab[data-tab="prv"]'); pg.wait_for_timeout(1500)
    assert pg.locator("#prvPanel").is_visible() and not pg.locator("#dlmPanel").is_visible()
    pg.click("#settingsBtn"); pg.wait_for_timeout(1000)
    gs = pg.eval_on_selector_all("#settingsBody > details.settingsGroup", "els => els.map(e => e.querySelector('summary').textContent.trim())")
    assert gs[:6] == ["⚡ Лимитки 4ч+2ч", "P/R — Peak Reversal", "🧱 SMC", "📐 EMA — касания", "🔄 Классика наоборот", "📏 HTF-уровни"], gs
    pg.screenshot(path="ui_settings_order.png")
    print(tabs); print(gs)
    assert not errs, errs
    b.close()
print("t_tab_order OK")
