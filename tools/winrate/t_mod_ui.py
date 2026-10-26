"""v0.99.715 — the P/R / SMC / EMA tabs: a virtual open trade says why it is not on the exchange, a closed one says
whether it was there (the user: "сделка закрылась тейком, но её нигде нет"), all the open ones listed, no page errors"""
import time, threading
from common import V
now = int(time.time()); h = now // 3600 * 3600
V.AUTOTRADE_ENABLED_PRV = V.AUTOTRADE_ENABLED_SMC = V.AUTOTRADE_ENABLED_EMW = V.AUTOTRADE_ENABLED_HTF = True; V.AUTOTRADE_DRY_RUN = False   # v0.99.732 — 📏 HTF too
base = lambda i, sym, st, **k: dict({"id": f"x{i}", "symbol": sym, "side": 1, "direction": "LONG", "entry": 1.0, "px": 1.0, "sl": 0.95, "tp": 1.1, "hs": 0.9,
                                     "hour": h - 7200 - i, "t_in": h - 7200 - i, "until": h + 86400, "status": st, "result": None, "r": None, "exit": None,
                                     "t_out": None, "real": False, "tf": 1, "n": 50, "fam": "fvg_bull", "rv": V.SMC_MODEL_VER, "sel": True}, **k)
opn = [base(i, f"C{i}_USDT", "OPEN", autotrade={"status": "SKIPPED", "detail": f"причина {i}"}) for i in range(14)]   # more than the old 10
cl = [base(99, "ZZ_USDT", "CLOSED", result="WIN", r=1.2, exit=1.1, t_out=h - 3600, autotrade={"status": "SKIPPED", "detail": "по монете уже есть позиция"})]
for mod, store, lk in (("prv", V._PRX, V._prx_lock), ("smc", V._SMC, V._smc_lock), ("emw", V._EMX, V._emx_lock), ("htf", V._HTF, V._htf_lock)):
    with lk:
        store["trades"] = [dict(t) for t in opn + cl]
for f in ("prx_save", "smc_save", "emx_save", "htf_save"):
    if hasattr(V, f): setattr(V, f, lambda: None)
threading.Thread(target=lambda: V.app.run(port=5107, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
res = {}
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium"); pg = b.new_page(viewport={"width": 420, "height": 900})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:5107/"); pg.wait_for_timeout(3000)
    for tab, panel in (("prv", "prvPanel"), ("smc", "smcPanel"), ("emw", "emwPanel"), ("htf", "htfPanel")):
        pg.click(f'.tab[data-tab="{tab}"]'); pg.wait_for_timeout(3000)
        html = pg.locator(f"#{panel}").inner_html(); txt = pg.locator(f"#{panel}").inner_text()
        pg.screenshot(path=f"ui_{tab}_why.png", full_page=True)
        res[tab] = ("не на бирже: причина 3" in txt and "не на бирже: причина 13" in txt and "виртуально" in txt
                    and "виртуально — на бирже её не было: по монете уже есть позиция" in html and "на бирже 0, виртуально 1" in txt)
        if not res[tab]: print(tab, txt[:1500])
    res["no page errors"] = not errs
    if errs: print(errs)
    b.close()
print(" · ".join(f"{k} {v}" for k, v in res.items()))
ok = all(res.values()); print("ALL OK" if ok else "FAILED"); import sys; sys.exit(0 if ok else 1)
