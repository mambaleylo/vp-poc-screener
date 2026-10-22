import time, threading, json
from common import V
import s15_engine as E
_BTD = json.load(open("vp_bt_trades_v679.json")); V.bt_trades = lambda: _BTD
def fake_bars(symbol, ch, start, end):
    T, O, H, L, C, Vv = E.load15(symbol.replace("_USDT", "") + "USDT")
    return [{"time": int(t), "open": o, "high": h, "low": l, "close": c} for t, o, h, l, c in zip(T, O, H, L, C) if start <= t <= end]
V.bt_gate_bars = fake_bars
threading.Thread(target=lambda: V.app.run(port=5104, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium"); pg = b.new_page(viewport={"width": 420, "height": 900})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:5104/"); pg.wait_for_timeout(2500)
    pg.evaluate("""() => { const t = window._btTmp = %s; btChart(Object.assign({mod: 'dlm'}, t)); }""" % json.dumps([x for x in _BTD["dlm"] if x["s"] == "ORDI_USDT" and abs(x["e"] - 4.83662) < 1e-4][0]))
    pg.wait_for_timeout(3000)
    pg.screenshot(path="ui_dlm_chart.png")
    print(pg.locator("#vgiModalParams").inner_text()); print("errors", errs); b.close()
