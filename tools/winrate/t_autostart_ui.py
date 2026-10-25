"""v0.99.721 — the page with the autostart button: no page errors; the button shows the status (the dialog dismissed)"""
import time, threading
from common import V
threading.Thread(target=lambda: V.app.run(port=5109, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium"); pg = b.new_page(viewport={"width": 420, "height": 900})
    errs, dlg = [], []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("dialog", lambda d: (dlg.append(d.message), d.dismiss()))
    pg.goto("http://127.0.0.1:5109/"); pg.wait_for_timeout(3000)
    pg.evaluate("autostartUi()"); pg.wait_for_timeout(2000)
    ok = not errs and dlg and "Автозапуск сейчас" in dlg[0] and "Termux:Boot" in dlg[0] and "\n" in dlg[0]
    print("errors", errs, "· dialog", (dlg[0][:160] if dlg else None))
    print("ALL OK" if ok else "FAILED")
    b.close()
