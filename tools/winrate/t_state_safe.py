"""v0.99.791 — the bundle's survival (the user: "проверку на стабильность и сохранение данных, живучесть при перезапусках, бэкапы,
подхваты после перезапусков"). Each of ⚡ / EMA / P/R / SMC / HTF / Классика / Binance's records / the settings:
(A) a save before the load writes nothing (was: the empty state over the real file);
(B) a broken file -> the .bak is read, the broken one kept aside, told in Telegram (was: "no trades" silently, then written over);
    both broken -> an empty start, told, the broken files kept;
(C) saves from 6 threads at once: no error, the file whole at every read (was: thousands of "No such file", a broken file);
(D) a save -> load round trip; the previous state stays as .bak; no stray .tmp;
(E) a stop: no new exchange operation, the one in flight ends first; then every module of the bundle is saved;
(F) the boot guard: 3 starts in a row that died right after an update -> the old version back, the bad one remembered and not
    taken by the auto-update again; a healthy run / a deliberate stop / an old update -> no rollback;
(G) a hung loop of the bundle -> the bot restarts itself, at most once in 3 h;
(H) the take-over button waits for the files to be read"""
import os, sys, json, glob, time, threading, tempfile
from common import V
ok = True
def chk(nm, c):
    global ok
    print(("OK  " if c else "FAIL") + " " + nm); ok &= bool(c)
errs = []; V.log_error = lambda m: errs.append(str(m))
told = []; V.tg_outbox_push = lambda t: told.append(t)
D = tempfile.mkdtemp(prefix="vpsafe_")
V.DLM_STATE_FILE, V.EMX_STATE_FILE, V.PRX_STATE_FILE = (os.path.join(D, f"vp_{x}_state.json") for x in ("dlm", "emx", "prx"))
V.SMC_STATE_FILE, V.HTF_STATE_FILE, V.CFL_STATE_FILE = (os.path.join(D, f"vp_{x}_state.json") for x in ("smc", "htf", "cfl"))
V.BNO_FILE = os.path.join(D, "vp_bn_others.json"); V.SETTINGS_FILE = os.path.join(D, "vp_poc_settings.json")
MODS = [("⚡", "DLM_STATE_FILE", V._DLM, V.dlm_load, V.dlm_save, "trades"), ("EMA", "EMX_STATE_FILE", V._EMX, V.emx_load, V.emx_save, "trades"),
        ("P/R", "PRX_STATE_FILE", V._PRX, V.prx_load, V.prx_save, "trades"), ("SMC", "SMC_STATE_FILE", V._SMC, V.smc_load, V.smc_save, "trades"),
        ("HTF", "HTF_STATE_FILE", V._HTF, V.htf_load, V.htf_save, "trades"), ("Классика", "CFL_STATE_FILE", V._CFL, V.cfl_load, V.cfl_save, "trades"),
        ("Binance-записи", "BNO_FILE", V._BNO, V.bno_load, V.bno_save, "pos")]
def good(key, n=50):
    return {key: ([{"id": i, "status": "OPEN", "symbol": "X_USDT", "t_in": 1, "hour": 1, "real": {"id": "1"}} for i in range(n)] if key == "trades"
                  else {f"C{i}_USDT": {"mode": "prv", "bsym": f"C{i}USDT"} for i in range(n)})}
def n_in(fn, key):
    try: return len(json.load(open(fn)).get(key) or [])
    except Exception as e: return f"не читается ({type(e).__name__})"
empty = lambda key: [] if key == "trades" else {}
a_ok = b_ok = b2_ok = c_ok = d_ok = True
for nm, fa, st, ld, sv, key in MODS:
    fn = getattr(V, fa)
    # (A)
    json.dump(good(key), open(fn, "w")); st[key] = empty(key); st.pop("loaded", None); sv()
    a = n_in(fn, key) == 50; a_ok &= a
    # (D) the round trip, the .bak, no stray .tmp
    ld(); d1 = len(st[key]) == 50 and st.get("loaded")
    st[key] = good(key, 30)[key]; sv(); st[key] = empty(key); ld()
    d = d1 and len(st[key]) == 30 and n_in(fn + ".bak", key) == 50 and not glob.glob(fn + ".*.tmp*"); d_ok &= d
    # (B) the main file cut in half -> the .bak (the 50), the broken one aside, told
    raw = open(fn).read(); open(fn, "w").write(raw[:len(raw) // 2]); told.clear(); st[key] = empty(key); ld()
    b = len(st[key]) == 50 and len(glob.glob(fn + ".bad-*")) == 1 and len(told) == 1 and "предыдущая копия" in told[0]
    sv(); b &= n_in(fn, key) == 50; b_ok &= b
    # both broken -> an empty start, told, nothing silently
    for x in (fn, fn + ".bak"): open(x, "w").write('{"tra')
    told.clear(); st[key] = empty(key); ld()
    b2 = len(st[key]) == 0 and len(told) == 1 and "запасной копии нет" in told[0] and len(glob.glob(fn + "*.bad-*")) >= 2; b2_ok &= b2
    # (C)
    errs.clear(); bad = [0]; stop = [False]; st["loaded"] = True; sv()
    def writer(k):
        i = 0
        while not stop[0]:
            st[key] = ([{"id": j, "status": "OPEN", "symbol": "X_USDT", "t_in": 1, "hour": 1, "pad": "x" * ((i * 7 + k * 13) % 400)} for j in range(40 + (i + k) % 30)]
                       if key == "trades" else {f"C{j}_USDT": {"mode": "prv", "bsym": "x" * ((i * 7 + k) % 300)} for j in range(20 + (i + k) % 20)})
            sv(); i += 1
    def reader():
        while not stop[0]:
            try: json.load(open(fn))
            except Exception: bad[0] += 1
    th = [threading.Thread(target=writer, args=(k,)) for k in range(6)] + [threading.Thread(target=reader)]
    for t in th: t.start()
    time.sleep(1.5); stop[0] = True
    for t in th: t.join()
    c = not errs and not bad[0] and not isinstance(n_in(fn, key), str); c_ok &= c
    if not (a and b and b2 and c and d): print(f"   {nm}: A {a} B {b} B2 {b2} C {c} (ошибок {len(errs)}, битых чтений {bad[0]}) D {d}")
chk("(A) запись до загрузки ничего не пишет — все 7 файлов", a_ok)
chk("(D) запись → чтение, прежнее состояние в .bak, лишних .tmp нет", d_ok)
chk("(B) испорченный файл: взята копия .bak, испорченный отложен, сказано в Telegram", b_ok)
chk("(B) испорчены оба: пустой старт, сказано, файлы отложены", b2_ok)
chk("(C) 6 потоков пишут сразу: ни одной ошибки, файл цел при каждом чтении", c_ok)
# an older snapshot never lands over a newer one: the snapshot and the write are one step per file
V._EMX["loaded"] = True; V._EMX["trades"] = [{"id": 1, "status": "OPEN", "symbol": "X_USDT", "t_in": 1}]
_dumps = V.json.dumps; gate = threading.Event(); first = [True]
def slow_dumps(o, **k):
    r = _dumps(o, **k)
    if first[0] and isinstance(o, dict) and "armed_at" in o:   # the first saver: its snapshot taken, held before the write
        first[0] = False; gate.wait(1.0)
    return r
V.json.dumps = slow_dumps
try:
    ta = threading.Thread(target=V.emx_save); ta.start(); time.sleep(0.2)
    V._EMX["trades"] = V._EMX["trades"] + [{"id": 2, "status": "OPEN", "symbol": "Y_USDT", "t_in": 2}]
    tb = threading.Thread(target=V.emx_save); tb.start(); time.sleep(0.2); gate.set(); ta.join(); tb.join()
finally:
    V.json.dumps = _dumps
chk("(C) старый снимок не ложится поверх нового (в файле обе сделки)", n_in(V.EMX_STATE_FILE, "trades") == 2)
# the settings: the same
V._SETTINGS_IO["loaded"] = False; json.dump({"marker": 1}, open(V.SETTINGS_FILE, "w")); V.save_settings()
chk("настройки: запись до загрузки ничего не пишет", json.load(open(V.SETTINGS_FILE)) == {"marker": 1})
V.load_settings(); V.save_settings(); s1 = json.load(open(V.SETTINGS_FILE))
raw = open(V.SETTINGS_FILE).read(); V.save_settings(); open(V.SETTINGS_FILE, "w").write(raw[:200]); told.clear(); V.load_settings()
chk("настройки: испорченный файл — взята копия, сказано", len(told) == 1 and "настройки бота" in told[0] and len(s1) > 20)
V.save_settings(); chk("настройки после этого целы", json.load(open(V.SETTINGS_FILE)) == s1)
# (E) a stop waits for the exchange operation in flight, then saves the bundle
V._XOP["stop"] = 0.0; log = []
@V.exchange_guarded
def slow_op():
    log.append("op start"); time.sleep(0.6); log.append("op end")
@V.exchange_guarded
def new_op():
    log.append("new op ran")
t1 = threading.Thread(target=slow_op); t1.start(); time.sleep(0.1)
t0 = time.time(); q = V.exchange_quiesce(5); log.append("quiet")
t2 = threading.Thread(target=new_op, daemon=True); t2.start(); time.sleep(0.4)
chk(f"(E) остановка дождалась операции на бирже ({time.time() - t0:.1f} с), новая не началась: {log}", q and log == ["op start", "op end", "quiet"])
V._XOP["stop"] = 0.0; t2.join(2); chk("(E) после снятия остановки операции идут", log[-1] == "new op ran")
@V.exchange_guarded
def stuck_op():
    time.sleep(1.2)
threading.Thread(target=stuck_op, daemon=True).start(); time.sleep(0.1)
chk("(E) операция не закончилась за отведённое время — остановка не ждёт вечно", V.exchange_quiesce(0.3) is False)
V._XOP["stop"] = 0.0; time.sleep(1.3)
saved = []
for f in ("save_state", "save_neuro_state", "save_nq_state", "save_settings", "zones_save", "_zones_outbox_save", "dlm_save", "bno_save", "emx_save",
          "prx_save", "smc_save", "htf_save", "cfl_save"):
    setattr(V, f, (lambda n: (lambda: saved.append(n)))(f))
V.save_everything_before_exit(wait_tg=0, quiet=0.1); V._XOP["stop"] = 0.0
chk(f"(E) перед остановкой сохраняются и модули связки: {saved[6:]}", set(saved) >= {"dlm_save", "bno_save", "emx_save", "prx_save", "smc_save", "htf_save", "cfl_save"})
# (F) the boot guard
B = tempfile.mkdtemp(prefix="vpboot_"); me = os.path.join(B, "vp_poc_screener.py"); V.BOOT_FILE = me + ".boot"
open(me, "w").write('APP_VERSION = "9.9.2"\nboom\n'); open(me + ".bak", "w").write('APP_VERSION = "9.9.1"\n')
V._boot_write({"upd_t": int(time.time()), "fails": 0}); rs = []
r = [V.boot_guard(me, restart=lambda: rs.append(1)) for _ in range(3)]
chk("(F) три упавших старта — ещё не откат", r == [False] * 3 and not rs and V._boot_read()["fails"] == 3)
r4 = V.boot_guard(me, restart=lambda: rs.append(1)); b = V._boot_read()
chk(f"(F) четвёртый старт: прежняя версия возвращена, плохая запомнена: {b}", r4 is True and rs == [1] and V._file_version(me) == "9.9.1"
    and b["bad"] == "9.9.2" and b["rolled"]["to"] == "9.9.1" and V._file_version(me + ".broken") == "9.9.2" and b["fails"] == 0)
class _Resp:
    status_code = 200; content = (b'APP_VERSION = "9.9.2"\napp.run(\n' + b"#" * 100001)
    def raise_for_status(self): pass
_get = V.requests.get; V.requests.get = lambda *a, **k: _Resp()
try:
    chk("(F) автообновление не ставит не запустившуюся версию снова", V.self_update_download(only_if_newer=True) == V.APP_VERSION)
finally:
    V.requests.get = _get
told.clear(); V.restart_note_on_start(); V.restart_note_on_start()
chk(f"(F) об откате сказано один раз: «{(told or [''])[0][:70]}…»", len(told) == 1 and "9.9.2" in told[0] and "9.9.1" in told[0])
open(me, "w").write('APP_VERSION = "9.9.3"\n'); open(me + ".bak", "w").write('APP_VERSION = "9.9.1"\n')
V._boot_write({"upd_t": int(time.time()) - 2 * 3600, "fails": 5, "t": int(time.time())})
chk("(F) падения не сразу после обновления (Android убил, перезагрузка) — отката нет", V.boot_guard(me, restart=lambda: rs.append(2)) is False and V._file_version(me) == "9.9.3")
V._boot_write({"upd_t": int(time.time()), "fails": 3, "t": int(time.time()) - 3000})
chk("(F) упавшие старты были давно (не цикл падений) — отката нет, счёт с нуля", V.boot_guard(me, restart=lambda: rs.append(3)) is False and V._boot_read()["fails"] == 1 and 3 not in rs)
V._boot_write({"upd_t": int(time.time()), "fails": 2}); V.boot_clear()
chk("(F) живой запуск / намеренная остановка обнуляют счёт", V._boot_read()["fails"] == 0)
# (G) a hung loop of the bundle
V._boot_write({}); rs = []; told.clear()
st_ = [{"name": "dlm_loop", "label": "⚡ Лимитки", "silent_min": 31, "max_gap_min": 30}]
g1 = V.stall_restart_check(st_, restart=lambda why, d: rs.append(why)); g2 = V.stall_restart_check(st_, restart=lambda why, d: rs.append(why))
g3 = V.stall_restart_check(st_, now=time.time() + 3 * 3600 + 5, restart=lambda why, d: rs.append(why))
chk(f"(G) завис ⚡ — бот перезапускается сам, не чаще раза в 3 ч: {rs}", g1 == "dlm_loop" and g2 is None and g3 == "dlm_loop" and rs == ["stall", "stall"] and "Перезапускаю" in told[0])
V._boot_write({}); chk("(G) зависший поток не из связки — только предупреждение, как раньше",
                       V.stall_restart_check([{"name": "snr_backtest_loop", "label": "x", "silent_min": 99, "max_gap_min": 60}], restart=lambda *a: rs.append(9)) is None and 9 not in rs)
chk("(G) поток позиций модулей на Binance теперь под присмотром", "bno_loop" in V.LOOP_MAX_GAP_SEC and "bno_loop" in V.STALL_RESTART_LOOPS)
# (H) the take-over button
V._DLM["loaded"] = False; V.DLM_ENABLED = V.DLM_BINANCE = V.AUTOTRADE_ENABLED_DLM = True; V.BINANCE_API_KEY = V.BINANCE_API_SECRET = "k" * 20; V.AUTOTRADE_DRY_RUN = False
called = []; V.dlm_bn_adopt = lambda *a: called.append(1) or []
with V.app.test_client() as c:
    j = c.post("/api/dlm/adopt").get_json()
    chk(f"(H) кнопка «подхватить» до чтения записей: «{j.get('err')}»", j["ok"] is False and not called)
    V._DLM["loaded"] = V._BNO["loaded"] = True; j = c.post("/api/dlm/adopt").get_json(); chk("(H) после чтения — работает", j["ok"] is True and called)
print("t_state_safe OK" if ok else "t_state_safe FAIL")
