import time, threading
from common import V, load
for f in ("zm_model", "emx_model", "nx_model", "prx_model", "cas_model"):
    try: getattr(V, f)()
    except Exception as e: print("model", f, e)
threading.Thread(target=lambda: V.app.run(port=5100, use_reloader=False), daemon=True).start()
time.sleep(2)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium"); pg = b.new_page(viewport={"width": 420, "height": 900})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:5100/"); pg.wait_for_timeout(3000)
    for tab in ("prv", "emw", "zones", "neuro", "rbx", "cas", "signals", "autotrade"):
        try:
            pg.click(f'.tab[data-tab="{tab}"]'); pg.wait_for_timeout(3500)
            pg.screenshot(path=f"all_{tab}.png", full_page=True)
            txt = pg.locator("body").inner_text()
            open(f"all_{tab}.txt", "w").write(txt)
            print(tab, "ok", len(txt))
        except Exception as e:
            print(tab, "ERR", str(e)[:120])
    print("errors", errs)
    b.close()
