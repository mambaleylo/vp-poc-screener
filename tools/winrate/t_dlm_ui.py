"""v0.99.687 — the ⚡ 4h tab renders (a virtual order, an open and a closed trade, the backtest list and its chart) with no
page errors; the old single / ladder switches are gone"""
import time, threading, json
from common import V
V.dlm_model(); now = int(time.time()); tb = now // 14400 * 14400
V._DLM["scan"] = {"t": now, "bar": tb, "coins": 210, "cands": 300, "orders": 1, "near": [{"symbol": "SOL_USDT", "side": 1, "pct": 88}], "src": {"binance": 210, "gate": 0}}
V._DLM["orders"] = [{"id": "o1", "symbol": "SOL_USDT", "side": 1, "lv": 148.2, "atr": 3.1, "score": 0.4, "t0": tb, "bs": 14400, "until": tb + 4 * 14400, "px": 155.4, "status": "OPEN", "real": None}]
V.AUTOTRADE_ENABLED_DLM = True; V.AUTOTRADE_DRY_RUN = True   # v0.99.701 — a virtual open trade says why it is not on the exchange
V._DLM["trades"] = [{"id": "t1", "symbol": "DOGE_USDT", "side": -1, "direction": "SHORT", "entry": 0.21, "lv": 0.21, "atr": 0.004, "sl": 0.218, "tp": 0.206, "score": 0.4, "t0": tb - 14400, "fbar": tb - 14400, "t_in": now - 6000, "until": tb + 30 * 14400, "bs": 14400, "hold": 32, "status": "OPEN", "result": None, "r": None, "real": None, "rv": 2},
                    {"id": "t2", "symbol": "ADA_USDT", "side": 1, "direction": "LONG", "entry": 0.5, "lv": 0.5, "atr": 0.01, "sl": 0.48, "tp": 0.51, "score": 0.4, "t0": tb - 8 * 14400, "fbar": tb - 7 * 14400, "t_in": now - 99000, "until": 0, "bs": 14400, "hold": 32, "status": "CLOSED", "result": "WIN", "r": 0.49, "exit": 0.51, "t_out": now - 30000, "real": None, "rv": 2},
                    {"id": "t3", "symbol": "XRP_USDT", "side": 1, "direction": "LONG", "entry": 2.0, "lv": 2.0, "atr": 0.01, "sl": 1.98, "tp": 2.005, "score": 0.1, "t0": tb - 99999, "fbar": tb - 99000, "t_in": now - 99000, "until": 0, "status": "CLOSED", "result": "WIN", "r": 0.22, "exit": 2.005, "t_out": now - 90000, "real": None, "rv": 1}]
V.dlm_save = lambda: None
_BTD = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json")); V.bt_trades = lambda: _BTD
import s20h4_engine as E
import os; os.environ["TFH"] = "2"
import s21h2_engine as E2   # v0.99.689 — the 2h stream's charts
seen_ch = []
def fake_bars(symbol, ch, start, end):
    seen_ch.append(ch)
    T, O, H, L, C, Vv = (E2 if ch == "2h" else E).load15(symbol.replace("_USDT", "") + "USDT")
    return [{"time": int(t), "open": o, "high": h, "low": l, "close": c} for t, o, h, l, c in zip(T, O, H, L, C) if start <= t <= end]
V.bt_gate_bars = fake_bars
threading.Thread(target=lambda: V.app.run(port=5103, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium"); pg = b.new_page(viewport={"width": 420, "height": 900})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:5103/"); pg.wait_for_timeout(3000)
    html = pg.content()
    pg.click('.tab[data-tab="dlm"]'); pg.wait_for_timeout(3000)
    pg.screenshot(path="ui_dlm.png", full_page=True)
    txt = pg.locator("#dlmPanel").inner_text(); print(txt[:1500])
    pg.click("#dlmPanel details summary >> text=Сделки бэктеста"); pg.wait_for_timeout(3000)
    print("bt:", pg.locator("#btBox_dlm").inner_text()[:300])
    pg.locator("#btBox_dlm div[onclick^='btOpen']").first.click(); pg.wait_for_timeout(3000)
    pg.screenshot(path="ui_dlm_chart.png")
    print("chart:", pg.locator("#vgiModalTitle").inner_text())
    pg.keyboard.press("Escape"); pg.wait_for_timeout(500)
    pg.locator("#btBox_dlm div[onclick^='btOpen']", has_text="2ч").first.evaluate("e => e.click()"); pg.wait_for_timeout(3000)
    pg.screenshot(path="ui_dlm_chart2h.png")
    t2 = pg.locator("#vgiModalTitle").inner_text(); print("chart 2h:", t2, "· bars asked", sorted(set(seen_ch)))
    pg.keyboard.press("Escape"); pg.wait_for_timeout(500)
    # v0.99.693 — the user's TLM 2h long of 28.09 (out by time 30.09 20:00 UTC): its exit dot was drawn a day early (no '2h'
    # in the chart's bar length), and the 3 ATR emergency stop of the list was not drawn
    pg.evaluate("() => { const f = emwPanel; emwPanel = (c, box, bars, opt) => { window._dots = opt.dots; window._hl = opt.hlines; return f(c, box, bars, opt); }; }")
    i_tlm = next(i for i, t in enumerate(_BTD["dlm"]) if t["s"] == "TLM_USDT" and t["t"] == 1790553600)
    pg.evaluate("() => btOpen('dlm', window._btData.dlm.findIndex(t => t.s === 'TLM_USDT' && t.t === 1790553600))"); pg.wait_for_timeout(3000)
    pg.screenshot(path="ui_dlm_tlm.png")
    dots = pg.evaluate("() => window._dots"); hl = pg.evaluate("() => window._hl")
    tlm = _BTD["dlm"][i_tlm]
    exit_ok = dots[-1]["t"] == tlm["x"] - 7200 and abs(dots[-1]["p"] - tlm["xp"]) < 1e-12 and dots[0]["t"] == tlm["f"] // 7200 * 7200
    hs_ok = any(h["tag"] == "ав" and abs(h["p"] - tlm["sl2"]) < 1e-12 for h in hl)
    print("TLM 2h: entry dot", time.strftime("%d.%m %H:%M", time.gmtime(dots[0]["t"])), "· exit dot", time.strftime("%d.%m %H:%M", time.gmtime(dots[-1]["t"])), "(the exit bar)", exit_ok, "· emergency stop drawn", hs_ok)
    pg.keyboard.press("Escape")
    # v0.99.696 — the last 50 backtest trades: next to each one's R its $ and the account after it, from $100 with the
    # settings' risk, the bunches (20 at once), the margin by the bot's leverage — checked against an independent replica
    pg.evaluate("() => document.getElementById('vgiModal').classList.remove('open')"); pg.wait_for_timeout(300)
    pg.evaluate("() => btRender('dlm')"); pg.wait_for_timeout(500)
    pg.locator("#btBox_dlm").screenshot(path="ui_dlm_m50.png")
    rows = [l for l in pg.locator("#btBox_dlm").inner_text().split("\n") if "→ $" in l]
    import re as _re
    shown = [int(_re.sub(r"\D", "", l.split("→ $")[1].split("·")[0])) for l in rows]
    rk, mp, buf = V.dlm_risk(), V.DLM_MAX_POS, float(V.dlm_model().get("liq_buf") or 1.5)
    tr = sorted([t for t in _BTD["dlm"] if t.get("r") is not None], key=lambda t: (t["f"], t["t"], t["s"]))[-50:]
    eq, op, bal = 100.0, [], []
    def _settle(upto):
        global eq
        for p_ in sorted([p_ for p_ in op if p_[0] <= upto]): eq += p_[1] * p_[2]; op.remove(p_); bal.append(round(eq))
    for t in tr:   # the same bunches, independently: close what ended, a slot, the margin by the leverage at the emergency stop
        _settle(t["f"])
        if len(op) >= mp: continue
        st = max(0.002, abs(t["e"] - t["sl"]) / t["e"]); sth = abs(t["e"] - t["sl2"]) / t["e"]
        lev = min(20, int(1 / (buf * sth + 0.0105)))
        if lev < 1: continue
        ru = eq * rk / 100; mg = ru / st / lev; free = (eq - sum(p_[3] for p_ in op)) * 0.9
        if mg > free:
            ru *= max(0.0, free) / mg; mg = max(0.0, free)
        if ru / st < 5: continue   # v0.99.697 — under Binance's $5 position: not placed
        op.append((t["x"], t["r"], ru, mg))
    _settle(float("inf"))
    m50_ok = len(rows) >= 20 and all(any(abs(x - b_) <= 1 for b_ in bal) for x in shown) and max(shown) == max(bal) and len(bal) == len(pg.evaluate("() => (window._btData.dlm || []).filter(t => t._usd != null).length") * [0])
    # by the close: the account of a row = the one of the row below (the earlier close) + this row's $
    usd = [float(l.split("$")[1].split("→")[0].strip().replace(",", ".").replace("\u00a0", "")) * (-1 if "−$" in l else 1) for l in rows]
    seq_ok = all(abs(shown[i + 1] + usd[i] - shown[i]) <= 1.01 for i in range(len(rows) - 1))
    m50_ok = m50_ok and seq_ok
    if not seq_ok: print("SEQ", [(i, rows[i].strip()[:60], rows[i + 1].strip()[:60]) for i in range(len(rows) - 1) if abs(shown[i + 1] + usd[i] - shown[i]) > 1.01])
    print("rows with $:", len(rows), "· e.g.", rows[0].strip()[:120] if rows else "-", "· python final", bal[-1] if bal else None, m50_ok)
    why_ok = "не на бирже: включена «Бумажная торговля (dry-run)»" in txt and "виртуально — включена бумажная торговля" in txt
    print("virtual trade's reason shown", why_ok)
    # v0.99.714 — a closed virtual trade says so ("закрылась тейком, но на бирже её нет")
    closed_ok = "виртуально — на бирже её не было" in pg.content()
    why_ok = why_ok and closed_ok; print("closed virtual trade marked", closed_ok)
    gone = "setDlmSingle" not in html and "setDlmLadder" not in html and "Лесенка" not in txt
    print("errors", errs, "· why virtual", why_ok, "· last 50 money", m50_ok, "· TLM exit / emergency stop", exit_ok and hs_ok, "· single/ladder gone", gone, "· 4h text", "4ч" in txt and "старый модуль 15м" in txt, "· 2h chart", "2ч" in t2)
    b.close()
