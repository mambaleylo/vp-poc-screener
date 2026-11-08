"""v0.99.782 — the errors' levels (the user: "разграничить предупреждения и ошибки, а то красная выглядит как ошибка, по факту нет"):
the screenshot's 5 lines -> 3 warnings (GitHub 503/504, Binance connection reset) + 1 event (a model taken) + ... ; a real error
stays an error; the header's chip: red only with errors, amber with warnings only, grey with events only; each row tagged"""
import time, threading
from common import V
ok = True
def chk(nm, c):
    global ok
    print(("OK  " if c else "FAIL") + " " + nm); ok &= bool(c)
L = V.log_level
S = {"auto update: GitHub не ответил (503)": "warn", "auto update: GitHub не ответил (504)": "warn",
     "binance prices: Binance 0: нет связи: ('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer'))": "warn",
     "model refresh: 🔄 Классика наоборот — the repo's model taken (trained to 2025-12-18)": "info",
     "cfl time exit SOL_USDT: {'ok': True}": "info", "smc close stop ETH_USDT: {'ok': True}": "info",
     "execute_autotrade XRP_USDT: emergency SL placement ALSO failed (Read timed out)": "error",
     "cfl_loop: unsupported operand type(s) for +: 'int' and 'str'": "error", "dlm order BTC_USDT: KeyError 'qty'": "error"}
for m, want in S.items():
    chk(f"{want:5s} ← {m[:70]}", L(m) == want)
chk("русский текст GitHub 503 — не «необычная ошибка»", "временно" in V.error_to_russian("auto update: GitHub не ответил (503)"))
chk("русский текст обновления модели — «не ошибка»", "не ошибка" in V.error_to_russian("model refresh: P/R — the repo's model taken (trained to 2026-10-31)"))
# the app: only warnings / events -> no red chip
with V.state_lock:
    V.STATE["errors"].clear()
for m in list(S)[:4]: V.log_error(m)
threading.Thread(target=lambda: V.app.run(port=5141, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium"); pg = b.new_page(viewport={"width": 412, "height": 900})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:5141/"); pg.wait_for_timeout(4000)
    s1 = pg.evaluate("[document.getElementById('globalErrorsSum').className, document.getElementById('globalErrorsSum').innerText]")
    pg.evaluate("document.getElementById('globalErrorsBox').open = true"); pg.wait_for_timeout(500)
    rows = pg.evaluate("document.getElementById('globalErrorsList').innerText")
    pg.screenshot(path="/tmp/claude-0/err_lvl.png", clip={"x": 0, "y": 0, "width": 412, "height": 700})
    V.log_error("cfl_loop: unsupported operand type(s) for +: 'int' and 'str'"); pg.wait_for_timeout(16000)
    s2 = pg.evaluate("[document.getElementById('globalErrorsSum').className, document.getElementById('globalErrorsSum').innerText]")
    b.close()
chk(f"только предупреждения и событие — жёлтая плашка «Предупреждения»: {s1}", s1[0] == "warnTxt" and "Предупреждения 3" in " ".join(s1[1].split()) and "1 событ" in " ".join(s1[1].split()))
chk("в списке у строк метки «предупреждение» / «событие»", "● предупреждение" in rows and "● событие" in rows and "● ошибка" not in rows)
chk(f"появилась настоящая ошибка — красная «Ошибки 1»: {s2}", s2[0] == "loss" and "Ошибки 1" in " ".join(s2[1].split()))
chk("без ошибок JS", not errs)
print("t_err_lvl OK" if ok else "t_err_lvl FAIL")
