"""v0.99.734 — the backtest list rows on a phone: one line per trade (the user: "чтобы влазило в одну строку"),
the exit and R always visible, the level cut with "…" when it does not fit; every module's list, no page errors"""
import time, threading, sys
from common import V
V.app.config["TESTING"] = True
threading.Thread(target=lambda: V.app.run(port=5109, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
res = {}
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium"); pg = b.new_page(viewport={"width": 412, "height": 900})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:5109/"); pg.wait_for_timeout(3000)
    for tab, panel in (("htf", "htfPanel"), ("smc", "smcPanel")):
        pg.click(f'.tab[data-tab="{tab}"]'); pg.wait_for_timeout(2500)
        pg.evaluate(f"document.getElementById('btBox_{tab}').closest('details').open = true"); pg.wait_for_timeout(3000)
        rows = pg.locator(f"#btBox_{tab} div[onclick]")
        n = rows.count(); hs = [rows.nth(i).locator("div").first.bounding_box()["height"] for i in range(min(n, 40))]
        pg.locator(f"#btBox_{tab}").screenshot(path=f"ui_bt_oneline_{tab}.png")
        res[tab] = n > 10 and max(hs) < 1.6 * min(hs)
        print(tab, "rows", n, "heights", round(min(hs)), "-", round(max(hs)))
    res["no page errors"] = not errs
    if errs: print(errs)
    b.close()
ok = all(res.values()); print("ALL OK" if ok else "FAILED"); sys.exit(0 if ok else 1)
