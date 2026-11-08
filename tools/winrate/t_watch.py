"""v0.99.784 — the live-vs-backtest watchdog: (1) the backtest's own limits from vp_bt_trades.json (the lab's numbers);
(2) the rule's cases (too early under 20 trades, the average below the bound, a streak / drawdown / pause beyond the backtest's
worst, ⚡'s slippage); (3) the messages: once when a warning appears, nothing an hour later, a reminder after 7 days,
"снова в норме" when clear, the comparison restarted by a new model / rule; nothing switched off or changed, the module's
trades untouched; the log's level a warning; (4) the settings block in the app"""
import time, json, copy, threading, os, tempfile
from common import V
ok = True
def chk(nm, c):
    global ok
    print(("OK  " if c else "FAIL") + " " + nm); ok &= bool(c)
BT = V.bt_trades()
# (1) the backtest's limits
b = V.watch_bt_stats(BT["cfl"])
chk(f"Классика в бэктесте: R {b['mu']:+.2f}, серия {b['streak']}, просадка {b['dd']:.1f}R, пауза {b['gap'] / 86400:.0f} дн.",
    abs(b["mu"] - 2.11) < 0.01 and b["streak"] == 33 and abs(b["dd"] - 48.3) < 0.1 and abs(b["gap"] / 86400 - 135.2) < 0.1)
d_ = V.watch_bt_stats(BT["dlm"])
chk(f"⚡ в бэктесте: R {d_['mu']:+.2f}, серия {d_['streak']}, просадка {d_['dd']:.1f}R, пауза {d_['gap'] / 86400:.1f} дн.",
    abs(d_["mu"] - 0.26) < 0.01 and d_["streak"] == 21 and abs(d_["gap"] / 86400 - 27.2) < 0.1)
chk("меньше 30 сделок в бэктесте — не сравнивать", V.watch_bt_stats(BT["cfl"][:20]) is None)
# (2) the rule
now = time.time(); since = now - 30 * 86400
bs = {"mu": 0.5, "sd": 1.0, "wr": 60.0, "dd": 10.0, "streak": 5, "gap": 20 * 86400}
E = lambda rs, ent=None, slip=None: V.watch_eval(bs, [(since + i * 3600, r) for i, r in enumerate(rs)], ent if ent is not None else [now - 3600], since, now, slip)
m, W = E([-0.3] * 19); chk(f"19 сделок по −0.3R — судить рано, предупреждений нет ({list(W)})", "avg" not in W)
m, W = E([-0.3, 0.4] * 10); chk(f"20 сделок, в среднем {m['avg']:+.2f}R < граница {m['lo']:+.2f}R — предупреждение", "avg" in W and m["lo"] < 0.5)
m, W = E([0.3, 0.4] * 10); chk(f"в среднем {m['avg']:+.2f}R — в пределах (граница {m['lo']:+.2f}R)", not W)
m, W = E([1.0] * 10 + [-1.0] * 6); chk(f"6 убытков подряд при худших 5 в бэктесте — предупреждение ({m['streak']})", "streak" in W and "dd" not in W)
m, W = E([1.0] * 3 + [-1.0, 0.1] * 6 + [-1.0]); chk(f"просадка {m['dd']}R при худшей 10R — нет; серия 1 — нет", not W)
m, W = E([2.0] * 3 + [-2.0, 0.5] * 7); chk(f"просадка {m['dd']}R глубже 10R — предупреждение", "dd" in W)
P0 = V._PROC_START; V._PROC_START = now - 60 * 86400   # the bot running for 60 days (a pause counts from the bot's start: its downtime is not the module's)
m, W = E([0.5] * 5, ent=[now - 25 * 86400]); chk(f"{m['pause_d']} дн. без сделок при самой длинной паузе 20 — предупреждение", "pause" in W)
V._PROC_START = now - 5 * 86400
m, W = E([0.5] * 5, ent=[now - 25 * 86400]); chk(f"бот запущен 5 дн. назад — пауза {m['pause_d']} дн. (время выключенного бота не в счёт)", "pause" not in W and abs(m["pause_d"] - 5) < 0.1)
V._PROC_START = P0
m, W = E([0.5] * 5, ent=[now - 10 * 86400]); chk("10 дн. — в пределах", "pause" not in W)
m, W = E([0.5] * 5, slip=[-0.15] * 20); chk(f"⚡ исполнения хуже плана на 0.15R (20 сделок) — предупреждение", "slip" in W)
m, W = E([0.5] * 5, slip=[-0.15] * 19); chk("19 исполнений — рано", "slip" not in W)
m, W = E([0.5] * 5, slip=[-0.05] * 40); chk("хуже плана на 0.05R — в пределах", "slip" not in W)
# (3) the messages
d = tempfile.mkdtemp(); V.WATCH_STATE_FILE = os.path.join(d, "watch.json"); V._WATCH["st"] = None; V.WATCH_ENABLED = True
for _, _, _, _, _, flag in V._WATCH_MODS:
    setattr(V, flag, flag == "CFL_ENABLED")
sent = []; V.send_telegram = lambda t, category=None: sent.append((t, category))
logs = []; _le = V.log_error; V.log_error = lambda msg: logs.append(msg)
model = {"ver": 2, "trained_to": 1790000000, "rule": {"q": 0.995, "stop_datr": 0.4, "take_r": 8.0}, "trees": [[0] * 500]}
auto0, en0 = V.AUTOTRADE_ENABLED_CFL, V.CFL_ENABLED
T0 = time.time()
with V._cfl_lock:
    V._CFL["model"] = model
    V._CFL["trades"] = [{"status": "CLOSED", "r": -1.0, "t_in": T0 - 86400 * 3 - i * 3600, "t_out": T0 - 86400 * 2, "rv": V.CFL_MODEL_VER} for i in range(40)]
r = V.watch_check(T0)
chk(f"первая проверка: сравнение с этого момента, старые 40 убытков не в счёт (n {r['cfl']['n']})", r["cfl"]["n"] == 0 and not r["cfl"]["warn"] and not sent)
chk("другие модули выключены — их нет в проверке", list(r) == ["cfl"])
def add(rs, t):
    with V._cfl_lock:
        for i, x in enumerate(rs):
            V._CFL["trades"].append({"status": "CLOSED", "r": x, "t_in": t + i * 60, "t_out": t + i * 60 + 30, "rv": V.CFL_MODEL_VER})
add([-0.5, 0.2] * 13, T0 + 3600)
before = copy.deepcopy(V._CFL["trades"])
r = V.watch_check(T0 + 86400)
chk(f"26 сделок, в среднем {r['cfl']['avg']:+.2f}R < граница {r['cfl']['lo']:+.2f}R — одно сообщение", len(sent) == 1 and sent[0][1] == "watch" and "Классика" in sent[0][0])
print("   " + sent[0][0].replace("\n", "\n   "))
chk("в сообщении: бот ничего не отключал", "ничего не отключал" in sent[0][0])
chk(f"в журнале — как предупреждение: «{logs[-1][:70]}…» -> {V.log_level(logs[-1])}", logs and V.log_level(logs[-1]) == "warn")
chk("модуль не выключен, автоторговля не тронута, сделки те же", V.CFL_ENABLED == en0 and V.AUTOTRADE_ENABLED_CFL == auto0 and V._CFL["trades"] == before)
V.watch_check(T0 + 86400 + 3600); chk("через час — без повтора", len(sent) == 1)
V.watch_check(T0 + 86400 * 8 + 7200); chk("через 7+ дней — напоминание", len(sent) == 2 and "напоминание" in sent[1][0])
add([3.0] * 30, T0 + 86400 * 8 + 9000)
r = V.watch_check(T0 + 86400 * 9); chk(f"после 30 прибыльных: в среднем {r['cfl']['avg']:+.2f}R — «снова в норме»", len(sent) == 3 and "снова в норме" in sent[2][0])
V.watch_check(T0 + 86400 * 9 + 3600); chk("дальше тишина", len(sent) == 3)
pv = V.watch_check(T0 + 86400 * 9 + 7200, send=False); chk("предпросмотр (/api/watch) ничего не шлёт", len(sent) == 3 and pv["cfl"]["n"] == 56)
model2 = dict(model, rule=dict(model["rule"], take_r=6.0))
with V._cfl_lock:
    V._CFL["model"] = model2
r = V.watch_check(T0 + 86400 * 10); chk(f"новое правило — сравнение с нуля (n {r['cfl']['n']}, с {time.strftime('%d.%m', time.localtime(r['cfl']['since']))})", r["cfl"]["n"] == 0 and len(sent) == 3)
with V._cfl_lock:
    V._CFL["model"] = dict(model2, trees=[[1] * 500])
r = V.watch_check(T0 + 86400 * 11); chk("другие деревья при тех же правилах и пороге — не сброс", r["cfl"]["since"] == int(T0 + 86400 * 10))
r = V.watch_check(T0 + 86400 * 147); chk(f"{r['cfl']['pause_d']:.0f} дн. без сделок (в бэктесте самая длинная 135) — сообщение", len(sent) == 4 and "без новых сделок" in sent[3][0])
st = json.load(open(V.WATCH_STATE_FILE)); chk("состояние сохранено в файл", st["mods"]["cfl"]["warn"] and "pause" in st["mods"]["cfl"]["warn"])
chk("файл состояния в .gitignore", "vp_watch_state.json" in open(os.path.join(os.path.dirname(V.__file__), ".gitignore")).read())
V.log_error = _le
# (4) the app
V.WATCH_STATE_FILE = os.path.join(d, "watch2.json"); V._WATCH["st"] = None
for _, _, _, _, _, flag in V._WATCH_MODS:
    setattr(V, flag, True)
threading.Thread(target=lambda: V.app.run(port=5133, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b_ = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium"); pg = b_.new_page(viewport={"width": 412, "height": 900})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:5133/"); pg.wait_for_timeout(3000)
    vals = pg.evaluate("(() => { const g = document.getElementById('setWatchEnabled'); return [!!g, g && g.checked]; })()")
    pg.wait_for_timeout(2500)
    txt = pg.evaluate("(document.getElementById('watchStatus') || {}).innerText || ''")
    b_.close()
chk(f"настройка в приложении: {vals}, ошибок страницы {len(errs)}", vals == [True, True] and not errs)
chk(f"блок сторожа: «{txt[:160]}»", "Классика" in txt and "бэктест" in txt)
print("t_watch OK" if ok else "t_watch FAIL")
