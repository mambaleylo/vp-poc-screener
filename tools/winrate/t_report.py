"""v0.99.785 — the month's plan vs fact: (1) the plan from the backtest's months (the empty months counted); (2) the month before
(December -> November, January -> last December); (3) the money from Binance's income rows: the transfers apart, a non-USD
row skipped, each row given to the module whose real trade on that coin was open, the rest "не из сделок бота"; (4) the
report's text: per module the fact, the plan and the verdict; (5) the schedule: the 1st from 06:00 UTC once a month, the
preview sends / saves nothing; (6) the app"""
import time, json, os, threading, calendar, tempfile
from common import V
ok = True
def chk(nm, c):
    global ok
    print(("OK  " if c else "FAIL") + " " + nm); ok &= bool(c)
BT = V.bt_trades()
# (1) the plan
p = V.report_plan(BT["cfl"])
chk(f"Классика, месяц бэктеста: в среднем {p['mean']:+.1f}R, обычно {p['p10']:+.0f}…{p['p90']:+.0f}R, ~{p['n_month']:.0f} сделок, месяцев {p['months']}",
    15 < p["mean"] < 35 and p["p10"] <= 0 < p["p90"] and 10 < p["n_month"] < 15 and p["months"] >= 40)
L = [{"t": calendar.timegm((2023, 1, 5, 0, 0, 0)), "x": calendar.timegm((2023, 1, 6, 0, 0, 0)), "r": 1.0}] * 30 + \
    [{"t": calendar.timegm((2023, 4, 5, 0, 0, 0)), "x": calendar.timegm((2023, 4, 6, 0, 0, 0)), "r": 2.0}] * 5
p2 = V.report_plan(L); chk(f"пустые месяцы считаются: янв +30, фев 0, мар 0, апр +10 -> среднее {p2['mean']:.1f}", p2["months"] == 4 and abs(p2["mean"] - 10.0) < 1e-9)
# (2) the month before
r = V.report_month_range(calendar.timegm((2026, 12, 1, 7, 0, 0))); chk(f"1 декабря -> {r[2]}", r[2] == "ноябрь 2026" and r[0] == calendar.timegm((2026, 11, 1, 0, 0, 0)))
r = V.report_month_range(calendar.timegm((2027, 1, 1, 7, 0, 0))); chk(f"1 января -> {r[2]}", r[2] == "декабрь 2026" and r[3] == "2026-12")
# (3) the money
t0, t1 = calendar.timegm((2026, 11, 1, 0, 0, 0)), calendar.timegm((2026, 12, 1, 0, 0, 0)); T = lambda d, h=0: calendar.timegm((2026, 11, d, h, 0, 0))
row = lambda ts, kind, amt, sym, asset="USDT": (ts * 1000, kind, amt, asset, f"1|{kind}|{sym}|{asset}|{ts}")
rows = [row(T(3, 5), "REALIZED_PNL", 50.0, "BTCUSDT"), row(T(3, 5), "COMMISSION", -2.0, "BTCUSDT"), row(T(3, 9), "FUNDING_FEE", -0.5, "BTCUSDT"),
        row(T(10), "REALIZED_PNL", -20.0, "1000PEPEUSDT"), row(T(10), "COMMISSION", -1.0, "1000PEPEUSDT"),
        row(T(12), "REALIZED_PNL", 7.0, "ETHUSDT"),   # no bot trade on it then: manual
        row(T(15), "TRANSFER", 500.0, ""), row(T(16), "COMMISSION", -0.3, "BTCUSDT", "BNB"),
        row(calendar.timegm((2026, 10, 30, 0, 0, 0)), "REALIZED_PNL", 99.0, "BTCUSDT")]   # the month before
mods = {"dlm": [{"symbol": "BTC_USDT", "t_in": T(3, 1), "t_out": T(3, 5), "real": {"r_real": 1.2}}],
        "cfl": [{"symbol": "PEPE_USDT", "bsym": "1000PEPEUSDT", "t_in": T(9), "t_out": T(10), "real": True},
                {"symbol": "ETH_USDT", "t_in": T(20), "t_out": T(21), "real": True}]}
tot, per = V.report_money(rows, t0, t1, mods)
chk(f"итог месяца: сделки {tot['pnl']}, комиссии {tot['fee']}, фандинг {tot['fund']}, итог {tot['net']}", tot["pnl"] == 37.0 and tot["fee"] == -3.0 and tot["fund"] == -0.5 and abs(tot["net"] - 33.5) < 1e-9)
chk(f"пополнение отдельно ({tot['dep']}), комиссия в BNB и прошлый месяц не в счёт", tot["dep"] == 500.0)
chk(f"⚡: {per['dlm']['net']} (сделка + комиссия + фандинг через 8 ч после выхода)", abs(per["dlm"]["net"] - 47.5) < 1e-9)
chk(f"🔄 по 1000PEPE: {per['cfl']['net']}", abs(per["cfl"]["net"] + 21.0) < 1e-9)
chk(f"ETH без сделки бота в то время -> «не из сделок бота»: {per['other']['net']}", per["other"]["net"] == 7.0)
# (4) the text
for _, _, _, _, _, flag in V._WATCH_MODS:
    setattr(V, flag, flag in ("CFL_ENABLED", "DLM_ENABLED"))
with V._cfl_lock:
    V._CFL["trades"] = [{"status": "CLOSED", "r": -1.0, "t_in": T(2) + i, "t_out": T(3) + i, "rv": V.CFL_MODEL_VER} for i in range(20)] + \
                       [{"status": "CLOSED", "r": 5.0, "t_in": T(2), "t_out": calendar.timegm((2026, 10, 3, 0, 0, 0)), "rv": V.CFL_MODEL_VER}]   # October: not counted
with V._dlm_lock:
    V._DLM["trades"] = [{"status": "CLOSED", "r": 0.3, "t_in": T(5) + i, "t_out": T(6) + i, "rv": V.DLM_MODEL_VER, "symbol": "BTC_USDT",
                         "real": {"r_real": 0.25} if i < 10 else None} for i in range(70)]
V.BINANCE_API_KEY = V.BINANCE_API_SECRET = ""
rep = V.report_build(calendar.timegm((2026, 12, 1, 7, 0, 0))); txt = V.report_text(rep)
print("   " + txt.replace("\n", "\n   "))
c, d = rep["mods"]["cfl"], rep["mods"]["dlm"]
chk(f"Классика: 20 сделок −20R, октябрьская не в счёт -> {c['verdict']}", c["n"] == 20 and c["r"] == -20.0 and c["verdict"] == "low")
chk(f"⚡: 70 сделок +21R, на Binance 10 ({d['r_real']}R) -> {d['verdict']}", d["n"] == 70 and d["n_real"] == 10 and abs(d["r_real"] - 2.5) < 1e-9 and d["verdict"] in ("ok", "low"))
chk("в тексте: месяц, план, «ниже обычного», «Бот ничего не менял»", "ноябрь 2026" in txt and "план" in txt and "ниже обычного" in txt and "Бот ничего не менял" in txt)
V.BINANCE_API_KEY, V.BINANCE_API_SECRET = "k", "s"; V.bn_income_sync = lambda now=None: list(rows)
with V._dlm_lock:
    V._DLM["trades"][0].update(t_in=T(3, 1), t_out=T(3, 5))
rep = V.report_build(calendar.timegm((2026, 12, 1, 7, 0, 0))); txt = V.report_text(rep)
chk(f"с ключами — деньги в тексте: «{[l for l in txt.splitlines() if 'Binance за месяц' in l][0][:90]}»", "Binance за месяц: <b>+$34</b>" in txt and "не из сделок бота" in txt)
# (5) the schedule
d_ = tempfile.mkdtemp(); V.REPORT_STATE_FILE = os.path.join(d_, "r.json")
sent = []; V.send_telegram = lambda t, category=None: sent.append((t, category))
chk("1-е число 05:00 UTC — ждёт", V.report_check(calendar.timegm((2026, 12, 1, 5, 0, 0))) is None and not sent)
pv = V.report_check(calendar.timegm((2026, 12, 1, 7, 0, 0)), force=True); chk("предпросмотр — ничего не отправлено и не сохранено", pv and not sent and not os.path.exists(V.REPORT_STATE_FILE))
V.report_check(calendar.timegm((2026, 12, 1, 7, 0, 0))); chk("1-е число 07:00 — отправлено", len(sent) == 1 and sent[0][1] == "report" and "ноябрь 2026" in sent[0][0])
chk("в тот же месяц — больше нет", V.report_check(calendar.timegm((2026, 12, 9, 7, 0, 0))) is None and len(sent) == 1)
V.report_check(calendar.timegm((2027, 1, 3, 9, 0, 0))); chk("бот был выключен 1-го — отчёт позже в том же месяце", len(sent) == 2 and "декабрь 2026" in sent[1][0])
V.REPORT_ENABLED = False; chk("выключено — ничего", V.report_check(calendar.timegm((2027, 2, 1, 9, 0, 0))) is None and len(sent) == 2); V.REPORT_ENABLED = True
chk("vp_report_state.json в .gitignore", "vp_report_state.json" in open(os.path.join(os.path.dirname(V.__file__), ".gitignore")).read())
# (6) the app
V.BINANCE_API_KEY = V.BINANCE_API_SECRET = ""
threading.Thread(target=lambda: V.app.run(port=5135, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b_ = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium"); pg = b_.new_page(viewport={"width": 412, "height": 900})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:5135/"); pg.wait_for_timeout(3000)
    vals = pg.evaluate("(() => { const g = document.getElementById('setReportEnabled'); return [!!g, g && g.checked]; })()")
    pg.wait_for_timeout(2000)
    txt = pg.evaluate("(document.getElementById('reportStatus') || {}).innerText || ''")
    b_.close()
chk(f"настройка в приложении: {vals}, ошибок страницы {len(errs)}", vals == [True, True] and not errs)
chk(f"блок: «{txt[:120]}»", "Итоги" in txt and "Классика" in txt)
print("t_report OK" if ok else "t_report FAIL")
