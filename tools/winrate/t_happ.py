"""v0.99.789 — /happ: (1) "/happ" -> Happ's launcher activity (com.happproxy), "/happ https://…" -> happ://add/<url>, "/happ happ://…" as
is, anything else refused (never an arbitrary command); (2) the subscription link masked in the reply and never in the app's log;
(3) Android's refusal (a background launch) told with the fix; (4) only through bot_command from the user's chat, in /help"""
import shutil
from common import V
ok = True
def chk(nm, c):
    global ok
    print(("OK  " if c else "FAIL") + " " + nm); ok &= bool(c)
calls = []
class R:
    def __init__(self, rc=0, out="", err=""): self.returncode, self.stdout, self.stderr = rc, out, err
def run_ok(cmd, **kw):
    calls.append(cmd); return R(0, "Starting: Intent { act=" + cmd[3] + (" dat=" + cmd[5] if "-d" in cmd else "") + " }")
shutil.which = lambda x: "/data/data/com.termux/files/usr/bin/am" if x == "am" else None
logs = []; V.log_error = lambda m: logs.append(m)
SUB = "https://sub.example.org/secret-token-123"
r = V.happ_open("", run=run_ok)
chk(f"/happ -> лаунчер Happ: {calls[-1]}", calls[-1] == ["am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", "-p", "com.happproxy"] and "✅" in r)
r = V.happ_open(SUB, run=run_ok)
chk(f"/happ <ссылка> -> happ://add/<ссылка>", calls[-1] == ["am", "start", "-a", "android.intent.action.VIEW", "-d", "happ://add/" + SUB])
chk(f"ссылка скрыта в ответе: «{r[:120]}…»", "secret-token-123" not in r and "<ссылка>" in r and "удалить" in r)
r = V.happ_open("happ://add/" + SUB, run=run_ok)
chk("happ://… как есть", calls[-1][-1] == "happ://add/" + SUB and "secret-token-123" not in r)
n = len(calls); r = V.happ_open("rm -rf /", run=run_ok)
chk("посторонний текст — отказ, ничего не запущено", len(calls) == n and "Не понял" in r)
def run_bad(cmd, **kw):
    return R(0, "", "Warning: Activity not started, its current task has been brought to the front\nError: Activity not started, unable to resolve Intent")
r = V.happ_open(SUB, run=run_bad)
chk("Android не дал — честно и что сделать", "⚠️" in r and "Поверх других приложений" in r and "secret-token-123" not in r)
def run_exc(cmd, **kw): raise TimeoutError("am timed out")
r = V.happ_open("", run=run_exc); chk("завис / исключение — тоже сказано", "⚠️" in r)
chk("в журнал бота ничего не попало", not logs)
shutil.which = lambda x: None
chk("не Android — сказано", "не в Termux" in V.happ_open("", run=run_ok))
shutil.which = lambda x: "/usr/bin/am"
sent = []; V.tg_outbox_push = lambda t: sent.append(t)
V.subprocess = __import__("subprocess")
import subprocess as _sp; _orig = _sp.run; _sp.run = run_ok
try:
    chk("команда через bot_command", V.bot_command("/happ " + SUB) and sent and "secret-token-123" not in sent[-1])
finally:
    _sp.run = _orig
chk("в /help есть /happ", "/happ" in V.BOT_COMMANDS_HELP)
print("t_happ OK" if ok else "t_happ FAIL")
