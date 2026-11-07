"""v0.99.779 — the withdrawal advice: (1) the rule's cases (below the threshold, no new high, the share, the floor, the free
balance cap); (2) the transfers: a withdrawal / a top-up move the high-water mark and are no profit; (3) the bot's month by
month state = the lab's rule (money_arm2 wd=hs/0.3/5000/25000|wdmin=5000) on random paths, the user withdrawing the advice;
(4) the schedule: the first run only measures, the 1st of the month from 06:00 UTC sends once, the preview saves nothing;
(5) the settings block in the app"""
import time, json, calendar, random, threading, os, tempfile
from common import V
ok = True
def chk(nm, c):
    global ok
    print(("OK  " if c else "FAIL") + " " + nm); ok &= bool(c)
A = V.wd_advice
a = A(4000, 4000, 3000, 3500, 0); chk("ниже $5k — не выводить", a["w"] == 0 and a["kind"] == "below_min")
a = A(9000, 9000, 10000, 8000, 0); chk("ниже максимума — не выводить", a["w"] == 0 and a["kind"] == "no_gain")
a = A(12000, 12000, 10000, 9000, 0); chk(f"30% новой прибыли: $2000 x 0.3 = $600 ({a['w']})", a["w"] == 600 and a["kind"] == "pct" and a["prof"] == 3000)
a = A(30000, 30000, 29000, 26000, 0); chk(f"с $25k не меньше $5000 ({a['w']})", a["w"] == 5000 and a["kind"] == "floor" and abs(a["excess"] - 4000) < 1e-6)
a = A(100000, 100000, 50000, 60000, 0); chk(f"много новой прибыли — 30% больше минимума ({a['w']})", a["w"] == 15000 and a["kind"] == "pct")
a = A(30000, 2000, 20000, 25000, 0); chk(f"не больше свободных денег ({a['w']})", a["w"] == 2000 and a["capped"])
# (2) the transfers
a = A(15000, 15000, 20000, 18000, -5000); chk(f"вывод $5000 снижает максимум, это не убыток (максимум {a['hwm']}, месяц {a['prof']})", a["hwm"] == 15000 and a["prof"] == 2000)
a = A(25000, 25000, 10000, 10000, 10000); chk(f"пополнение $10k — не прибыль (новая прибыль {a['gain']}, месяц {a['prof']})", a["gain"] == 5000 and a["prof"] == 5000)
a = A(28000, 28000, 30000, 29000, -5000, excess=4000); chk(f"вывод минимума сверх прибыли не снижает максимум ниже прежнего (максимум {a['hwm']})", abs(a["hwm"] - 29000) < 1e-6)
# (3) the bot's state month by month = the lab's rule
def lab(path):
    eq, hwm, out = path[0], path[0], []
    for g in path[1:]:
        eq *= g; w = 0.3 * (eq - hwm) if eq > hwm else 0.0
        if eq >= 25000: w = max(w, 5000.0)
        if eq < 5000: w = 0.0
        w = max(0.0, min(w, eq)); w = float(int(w // 10) * 10); eq -= w; hwm = max(hwm, eq); out.append(w)   # the bot's rounding to $10 down
    return out
def bot(path):
    eq = path[0]; st = {"hwm": eq, "eq_m": eq, "excess": 0.0}; out = []; dep = 0.0
    for g in path[1:]:
        eq *= g; a = V.wd_advice(eq, eq, st["hwm"], st["eq_m"], dep, st["excess"]); w = a["w"]
        st = {"hwm": a["next_hwm"], "eq_m": eq, "excess": a["excess"]}
        eq -= w; dep = -w; out.append(w)   # the user withdraws it during the next month
    return out
rnd = random.Random(7); same = 0; N = 300
for _ in range(N):
    p = [rnd.choice([1000, 3000, 5000, 20000, 50000])] + [rnd.choice([0.6, 0.8, 0.95, 1.1, 1.4, 2.0, 3.0]) for _ in range(12)]
    L, B = lab(p), bot(p)
    same += all(abs(x - y) <= max(10.0, 0.001 * x) for x, y in zip(L, B))   # one $10 rounding step (a float at the edge: 5999.99… vs 6000)
chk(f"бот месяц за месяцем = правило лаборатории: {same}/{N} путей", same == N)
# (4) the schedule
d = tempfile.mkdtemp(); V.WD_STATE_FILE = os.path.join(d, "wd.json"); V._WDS["st"] = None
V.BINANCE_API_KEY, V.BINANCE_API_SECRET = "k", "s"; V.WD_ENABLED = True
acct = {"equity": 10000.0, "free": 9000.0, "wallet": 10000.0, "upnl": 0.0}; V.bnf_account = lambda: dict(acct)
rows = []; V.bn_income_sync = lambda now=None: list(rows); V._bn_usd_px = lambda a_: 1.0
sent = []; V.send_telegram = lambda t, category=None: sent.append((t, category))
t1 = calendar.timegm((2026, 11, 14, 12, 0, 0)); r = V.wd_check(t1)
chk("первый запуск — только замер, без сообщения", r and r["kind"] == "start" and not sent and V.wd_state()["hwm"] == 10000)
chk("в тот же месяц — ничего", V.wd_check(t1 + 86400) is None and not sent)
acct["equity"] = 14000.0; acct["free"] = 12000.0
chk("1-е число до 06:00 UTC — ждёт", V.wd_check(calendar.timegm((2026, 12, 1, 5, 0, 0))) is None and not sent)
pv = V.wd_check(calendar.timegm((2026, 12, 1, 7, 0, 0)), force=True)
chk(f"предпросмотр: совет {pv['w']}, ничего не сохранено и не отправлено", pv["w"] == 1200 and not sent and V.wd_state()["month"] == "2026-11")
r = V.wd_check(calendar.timegm((2026, 12, 1, 7, 0, 0)))
chk(f"1-е число 07:00 — совет отправлен: {r['w']}", r["w"] == 1200 and len(sent) == 1 and sent[0][1] == "wd" and "Вывести <b>$1 200</b>" in sent[0][0] and "ноябрь 2026" in sent[0][0])
print("   " + sent[0][0].replace("\n", "\n   "))
chk("второй раз в декабре — ничего", V.wd_check(calendar.timegm((2026, 12, 2, 7, 0, 0))) is None and len(sent) == 1)
rows.append((calendar.timegm((2026, 12, 3, 0, 0, 0)) * 1000, "TRANSFER", -1200.0, "USDT", "x1"))   # the user took it
acct["equity"] = 12500.0; acct["free"] = 11000.0
r = V.wd_check(calendar.timegm((2027, 1, 1, 9, 0, 0)))
chk(f"после вывода: максимум {r['hwm']} (14000 − 1200), прибыль месяца {r['prof']} (без вывода), совет {r['w']}", r["hwm"] == 12800 and r["prof"] == -300 and r["w"] == 0 and "Не выводить" in sent[-1][0])
# (5) the app
V._WDS["st"] = None
threading.Thread(target=lambda: V.app.run(port=5131, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium"); pg = b.new_page(viewport={"width": 412, "height": 900})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:5131/"); pg.wait_for_timeout(3000)
    vals = pg.evaluate("""(() => { const g = id => document.getElementById(id); return [!!g('setWdEnabled'), g('setWdEnabled') && g('setWdEnabled').checked,
        g('setWdPct') && g('setWdPct').value, g('setWdMin') && g('setWdMin').value, g('setWdFloor') && g('setWdFloor').value, g('setWdFloorBal') && g('setWdFloorBal').value]; })()""")
    pg.wait_for_timeout(2500)
    st_txt = pg.evaluate("(document.getElementById('wdStatus') || {}).innerText || ''")
    b.close()
chk(f"настройки в приложении: {vals}", vals[0] and vals[1] is True and [float(x) for x in vals[2:]] == [30, 5000, 5000, 25000] and not errs)
chk(f"блок совета: «{st_txt[:120]}»", "совет" in st_txt or "сейчас" in st_txt)
print("t_wd OK" if ok else "t_wd FAIL")
