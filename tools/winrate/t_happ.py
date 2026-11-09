"""v0.99.789/790 — /happ: (1) "/happ https://…" -> happ://add/<url>, "/happ happ://…" as is, a bare "/happ" or anything else -> a hint,
nothing started (never an arbitrary command; a launch by package doesn't resolve from Termux — the user's test); (2) Happ "brought to
the front" (it was running) is a success — the user's test: the subscription was refreshed; (3) then the bot's page is brought back
(VIEW http://127.0.0.1:<port>/) and the bot says whether the page said it is on screen (/api/boot?vis=visible); (4) the link masked
in every reply and never in the app's log; (5) Android's refusal told with the fix; (6) only through bot_command, in /help;
(7) the page restores its screensaver after another app covered it"""
import shutil, time as _t
from common import V
ok = True
def chk(nm, c):
    global ok
    print(("OK  " if c else "FAIL") + " " + nm); ok &= bool(c)
calls = []
class R:
    def __init__(self, rc=0, out="", err=""): self.returncode, self.stdout, self.stderr = rc, out, err
def run_ok(cmd, **kw):   # as on the user's phone: Happ running -> brought to the front
    calls.append(cmd)
    return R(0, "Starting: Intent { act=" + cmd[3] + " dat=" + cmd[5][:12] + "... }"
             + ("\nWarning: Activity not started, its current task has been brought to the front" if cmd[5].startswith("happ") else ""))
shutil.which = lambda x: "/data/data/com.termux/files/usr/bin/am" if x == "am" else None
logs = []; V.log_error = lambda m: logs.append(m)
SUB = "https://sub.example.org/sub/3/secret-token-123"
pushed = []; jobs = []
kw = dict(spawn=jobs.append, sleep=lambda s: None, push=pushed.append)
n = len(calls); r = V.happ_open("", run=run_ok, **kw)
chk("пустая /happ — подсказка, ничего не запущено", len(calls) == n and "/happ https://" in r and not jobs)
r = V.happ_open("rm -rf /", run=run_ok, **kw)
chk("посторонний текст — подсказка, ничего не запущено", len(calls) == n and not jobs)
r = V.happ_open(SUB, run=run_ok, **kw)
chk("/happ <ссылка> -> happ://add/<ссылка>", calls[-1] == ["am", "start", "-a", "android.intent.action.VIEW", "-d", "happ://add/" + SUB])
chk(f"«brought to the front» — не ошибка: «{r[:70]}…»", not r.startswith("⚠️") and len(jobs) == 1)
chk("ссылка скрыта в ответе, совет удалить", "secret-token-123" not in r and "удалить" in r)
# the page comes back and says so
def seen_run(cmd, **kw):
    out = run_ok(cmd)
    if cmd[5].startswith("http"): V._PAGE_SEEN["t"] = _t.time() + 1   # the page (off screen before) comes back
    return out
V._PAGE_SEEN["t"] = 0.0; jobs.pop()();
chk(f"затем страница бота: {calls[-1]}", calls[-1] == ["am", "start", "-a", "android.intent.action.VIEW", "-d", "http://127.0.0.1:8080/"])
chk(f"страница не отозвалась — предупреждение с советом: «{pushed[-1][:60]}…»", pushed[-1].startswith("⚠️") and "Поверх других приложений" in pushed[-1])
V.happ_open("happ://add/" + SUB, run=seen_run, **kw)
chk("happ://… как есть", calls[-1][-1] == "happ://add/" + SUB)
jobs.pop()()
chk(f"страница отозвалась — «{pushed[-1][:50]}»", pushed[-1].startswith("✅") and "secret-token-123" not in "".join(pushed))
# v0.99.790 — the page was on screen: Android dropped the launch from the background (the user's test: silence after 40 s)
V._PAGE_SEEN.update(t=_t.time(), hid=0.0); n = len(calls)
r = V.happ_open(SUB, run=run_ok, **kw); jobs.pop()()
chk(f"Happ не открылся (страница не ушла с экрана) — честно: «{pushed[-1][:60]}…»", pushed[-1].startswith("⚠️ Happ не открылся")
    and "Поверх других приложений" in pushed[-1] and len(calls) == n + 1 and "напишет, открылся ли Happ" in r)
def cover_run(cmd, **kw):   # Happ comes up: the page says it went off screen; the page comes back: it says so
    out = run_ok(cmd)
    if cmd[5].startswith("happ"): V._PAGE_SEEN["hid"] = _t.time() + 1
    else: V._PAGE_SEEN["t"] = _t.time() + 1
    return out
V._PAGE_SEEN.update(t=_t.time(), hid=0.0)
V.happ_open(SUB, run=cover_run, **kw); jobs.pop()()
chk(f"Happ открылся и страница вернулась — «{pushed[-1][:45]}»", pushed[-1].startswith("✅") and calls[-1][-1].startswith("http://127.0.0.1"))
def run_bad(cmd, **kw):
    return R(0, "Starting: Intent { act=android.intent.action.VIEW dat=happ://add/" + SUB + " }",
             "Error: Activity not started, unable to resolve Intent { dat=happ://add/" + SUB + " }")
r = V.happ_open(SUB, run=run_bad, **kw)
chk("Android не дал — честно и что сделать, ссылка скрыта", r.startswith("⚠️") and "Поверх других приложений" in r and "secret-token-123" not in r and not jobs)
def run_exc(cmd, **kw): raise TimeoutError("am timed out")
r = V.happ_open(SUB, run=run_exc, **kw); chk("завис / исключение — тоже сказано", r.startswith("⚠️"))
chk("в журнал бота ничего не попало", not logs)
shutil.which = lambda x: None
chk("не Android — сказано", "не в Termux" in V.happ_open(SUB, run=run_ok, **kw))
shutil.which = lambda x: "/usr/bin/am"
# through the Telegram command
sent = []; V.tg_outbox_push = lambda t: sent.append(t)
import subprocess as _sp, threading as _th; _orig, _oth = _sp.run, _th.Thread
class _NoThread:
    def __init__(self, target=None, **k): self.f = target
    def start(self): pass
_sp.run = run_ok; _th.Thread = _NoThread
try:
    chk("команда через bot_command", V.bot_command("/happ " + SUB) is not False and sent and not sent[-1].startswith("⚠️") and "secret-token-123" not in sent[-1])
finally:
    _sp.run, _th.Thread = _orig, _oth
chk("в /help есть /happ", "/happ" in V.BOT_COMMANDS_HELP)
# the page: says it is visible, the screensaver back after another app covered it
src = open(V.__file__).read()
chk("страница сообщает боту, что она на экране / ушла с него", "fetch('/api/boot?vis=visible'" in src and "fetch('/api/boot?vis=went_hidden'" in src and "'/api/boot?vis=' + document.visibilityState" in src)
chk("скринсейвер возвращается сам", "if (_ssHiddenOn && !_ssActive) { _ssHiddenOn = false; toggleScreensaver(); }" in src)
with V.app.test_client() as c:
    V._PAGE_SEEN["t"] = 0.0; c.get("/api/boot?vis=hidden"); h = V._PAGE_SEEN["t"]
    c.get("/api/boot?vis=visible"); chk("/api/boot?vis=visible отмечает время, hidden — нет", h == 0.0 and V._PAGE_SEEN["t"] > 0)
    V._PAGE_SEEN["hid"] = 0.0; c.get("/api/boot?vis=went_hidden"); chk("/api/boot?vis=went_hidden отмечает уход с экрана", V._PAGE_SEEN["hid"] > 0)
print("t_happ OK" if ok else "t_happ FAIL")
