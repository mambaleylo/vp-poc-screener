"""v0.99.668: the backtest chart warns when Gate's candles never reached a limit entry (the user's IO EMA trade)"""
import time, threading, json
from common import V, load
T0 = 1790172000
def gb(sym, ch, a, b):
    h = [dict(c) for c in (load(sym.replace("_", "")) or []) if a <= c["time"] <= b]
    for c in h:
        if sym == "IO_USDT" and c["time"] == T0: c["low"] = 0.1430      # Gate's shorter wick
    return h
V.bt_gate_bars = gb
threading.Thread(target=lambda: V.app.run(port=5099, use_reloader=False), daemon=True).start()
time.sleep(2)
from playwright.sync_api import sync_playwright
x = [t for t in json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))["emx"] if t["s"] == "IO_USDT" and t["t"] == T0][0]
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium"); pg = b.new_page(viewport={"width": 400, "height": 900})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:5099/"); pg.wait_for_timeout(2500)
    for nm, tr in (("IO (Gate wick short)", x), ("IO real wick", dict(x, s="IO_USDT", e=0.1440))):
        o = dict(tr, mod="emx"); pg.evaluate(f"btChart({json.dumps(o)})"); pg.wait_for_timeout(2500)
        print(nm, "->", pg.locator("#vgiModalParams").inner_text().replace("\n", " ")[:330])
        pg.click("#vgiCloseBtn"); pg.wait_for_timeout(400)
    print("errors", errs); b.close()
