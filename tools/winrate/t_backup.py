"""v0.99.785 — the daily backup: (1) what goes in: the modules' state, the settings and the extra state files — never a
credential / login / Telegram-account file, and a state file that holds a secret's value is left out; (2) the zip sent to
the user's own chat as a document (sendDocument, the zip opens, the files intact), no Telegram set -> nothing sent;
(3) the schedule: once a day from 01:00 UTC, not again that day, a failure logged; (4) the settings block in the app"""
import time, json, io, os, zipfile, threading, calendar
from common import V
ok = True
def chk(nm, c):
    global ok
    print(("OK  " if c else "FAIL") + " " + nm); ok &= bool(c)
import tempfile
D = tempfile.mkdtemp(prefix="vpbk_")   # the bot's folder for this test: a fresh empty one (nothing deleted anywhere)
V._BACKUP_DIR = D; V.BACKUP_LAST_FILE = os.path.join(D, "vp_backup_last.json")
KEY, SEC, TOK, GH = "BNKEYabcdef1234567890", "BNSECRETzyxw0987654321", "123456:TGTOKENqwertyuiop", "ghp_GITHUBTOKEN000111222"
V.BINANCE_API_KEY, V.BINANCE_API_SECRET, V.TELEGRAM_BOT_TOKEN, V.TELEGRAM_CHAT_ID, V.TELEGRAM_ENABLED = KEY, SEC, TOK, "777", True
V.github_token = lambda: GH
W = lambda fn, obj: json.dump(obj, open(os.path.join(D, fn), "w"))
W("vp_binance_credentials.json", {"key": KEY, "secret": SEC})
W("vp_github_credentials.json", {"token": GH})
W("vp_poc_module_credentials.json", {"gate": {"key": "GATEKEYlonglonglong1", "secret": "GATESECRETlonglong22"}})
W("vp_ui_auth.json", {"pass": "UIPASSWORDlong123456"})
W("vp_zones_tg_user.json", {"session": "TGSESSIONlonglong9999"})
W("vp_cfl_state.json", {"trades": [{"symbol": "XLM_USDT", "r": 2.1}]})
W("vp_dlm_state.json", {"trades": [{"symbol": "BTC_USDT", "r": -1.0}] * 1000})
W("vp_wd_state.json", {"month": "2026-11", "hwm": 1234.5})
W("vp_poc_settings.json", {"watch_enabled": True})
W("vp_smc_state.json", {"note": "leaked " + "GATESECRETlonglong22"})   # a state file holding a secret by mistake
files = V.backup_files()
chk(f"берутся состояния и настройки: {files}", {"vp_cfl_state.json", "vp_dlm_state.json", "vp_wd_state.json", "vp_poc_settings.json"} <= set(files))
chk("файлы с ключами / входом / аккаунтом Telegram не берутся", not any(x in " ".join(files) for x in ("credential", "auth", "tg_user")))
data, took, skipped = V.backup_zip()
z = zipfile.ZipFile(io.BytesIO(data)); names = z.namelist()
chk(f"файл, где оказался ключ, пропущен: {skipped}", "vp_smc_state.json" not in names and any(a == "vp_smc_state.json" for a, _ in skipped))
blob = b"".join(z.read(n) for n in names)
chk("ни одного ключа, токена или пароля в архиве", not any(x.encode() in blob for x in (KEY, SEC, TOK, GH, "GATEKEYlonglonglong1", "GATESECRETlonglong22", "UIPASSWORDlong123456", "TGSESSIONlonglong9999")))
chk("сделки в архиве целы", json.loads(z.read("vp_dlm_state.json"))["trades"][0]["r"] == -1.0 and len(json.loads(z.read("vp_dlm_state.json"))["trades"]) == 1000)
# (2) the sending
posts = []
class R:
    ok = True; status_code = 200
def post(url, data=None, files=None, timeout=None, json=None):
    posts.append((url, data, files)); return R()
V.requests.post = post
r = V.backup_send(calendar.timegm((2026, 11, 9, 1, 30, 0)))
chk(f"отправлено документом в ваш чат: {r.get('files')} файлов, {r.get('size')} байт", r["ok"] and len(posts) == 1 and posts[0][0].endswith("/sendDocument") and posts[0][1]["chat_id"] == "777")
fn_, raw, mime = posts[0][2]["document"]
chk(f"имя {fn_}, архив открывается", fn_.startswith("vp_backup_2026-11-09") and mime == "application/zip" and "vp_cfl_state.json" in zipfile.ZipFile(io.BytesIO(raw)).namelist())
print("   подпись: " + posts[0][1]["caption"].replace("\n", "\n   "))
chk("в подписи: ключей нет, как восстановить, что не вошло", "Ключей и паролей внутри нет" in posts[0][1]["caption"] and "распаковать" in posts[0][1]["caption"] and "vp_smc_state.json" in posts[0][1]["caption"])
# (3) the schedule
V.BACKUP_LAST_FILE = os.path.join(D, "vp_backup_last2.json"); posts.clear()
logs = []; V.log_error = lambda m: logs.append(m)
chk("00:30 UTC — ещё рано", V.backup_check(calendar.timegm((2026, 11, 10, 0, 30, 0))) is None and not posts)
r = V.backup_check(calendar.timegm((2026, 11, 10, 1, 5, 0))); chk("01:05 UTC — копия ушла", r and r["ok"] and len(posts) == 1)
chk("в тот же день — больше нет", V.backup_check(calendar.timegm((2026, 11, 10, 15, 0, 0))) is None and len(posts) == 1)
chk("на следующий день — снова", V.backup_check(calendar.timegm((2026, 11, 11, 2, 0, 0)))["ok"] and len(posts) == 2)
V.BACKUP_ENABLED = False; chk("выключено — ничего", V.backup_check(calendar.timegm((2026, 11, 12, 2, 0, 0))) is None and len(posts) == 2); V.BACKUP_ENABLED = True
R.ok = False; R.status_code = 400; V.time.sleep = lambda s: None
r = V.backup_check(calendar.timegm((2026, 11, 12, 2, 0, 0))); chk(f"Telegram не принял — в журнале: «{(logs or [''])[-1][:60]}»", not r["ok"] and logs and "резервная копия не отправлена" in logs[-1])
R.ok = True; R.status_code = 200
V.TELEGRAM_BOT_TOKEN = ""; chk("Telegram не настроен — ничего не уходит", not V.backup_send()["ok"]); V.TELEGRAM_BOT_TOKEN = TOK
chk("vp_backup_last.json в .gitignore", "vp_backup_last.json" in open(os.path.join(os.path.dirname(V.__file__), ".gitignore")).read())
# (4) the app
V.TELEGRAM_ENABLED = False; V.time.sleep = time.sleep
threading.Thread(target=lambda: V.app.run(port=5134, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b_ = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium"); pg = b_.new_page(viewport={"width": 412, "height": 900})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:5134/"); pg.wait_for_timeout(3000)
    vals = pg.evaluate("(() => { const g = document.getElementById('setBackupEnabled'); return [!!g, g && g.checked, !!document.getElementById('backupNowBtn')]; })()")
    pg.wait_for_timeout(2000)
    txt = pg.evaluate("(document.getElementById('backupStatus') || {}).innerText || ''")
    b_.close()
chk(f"настройка и кнопка в приложении: {vals}, ошибок страницы {len(errs)}", vals == [True, True, True] and not errs)
chk(f"блок: «{txt[:140]}»", "в архиве" in txt)
print("t_backup OK" if ok else "t_backup FAIL")
