"""v0.99.793 — the design: (1) the palette — the phone's theme decides (light: the warm paper, dark: the neutral graphite), a theme
fixed in Settings → Оформление wins and is kept on the device; the text is readable on its surface in both (WCAG contrast); the
charts' canvases are dark plates in the day theme; (2) the settings by meaning — 7 sections, every setting's id exactly once,
the bundle's modules first, each with the same three rows (the work, the trading, the notifications); a mirror switch and its
original move together both ways and the change is saved; the search finds a group by its own name and hides empty sections;
(3) no page errors in either theme"""
import re, time, threading
from common import V
ok = True
def chk(nm, c):
    global ok
    print(("OK  " if c else "FAIL") + " " + nm); ok &= bool(c)
threading.Thread(target=lambda: V.app.run(port=5113, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
def lum(rgb):
    f = lambda c: c / 12.92 if c <= .03928 else ((c + .055) / 1.055) ** 2.4
    r, g, b = [f(x / 255) for x in rgb]; return .2126 * r + .7152 * g + .0722 * b
cr = lambda a, b: (max(lum(a), lum(b)) + .05) / (min(lum(a), lum(b)) + .05)
hexrgb = lambda h: tuple(int(h.strip()[i:i + 2], 16) for i in (1, 3, 5))
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium", args=["--no-sandbox"])
    for th in ("dark", "light"):
        pg = b.new_page(viewport={"width": 390, "height": 844}, color_scheme=th)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
        pg.goto("http://127.0.0.1:5113/"); pg.wait_for_timeout(3000)
        chk(f"{th}: тема берётся с телефона", pg.evaluate("document.documentElement.getAttribute('data-theme')") == th)
        tok = pg.evaluate("""() => { const c = getComputedStyle(document.documentElement), o = {};
            for (const k of ['--tx', '--tx-2', '--tx-3', '--pos', '--neg', '--warn', '--acc', '--money', '--card', '--m-dlm', '--prv', '--m-smc', '--m-ema', '--m-cfl', '--m-htf', '--m-zones',
                             '--neuro', '--m-rbx', '--m-cas', '--m-rbs', '--m-hdg', '--snr']) o[k] = c.getPropertyValue(k).trim();
            return o; }""")
        surf = hexrgb(tok["--card"])   # the solid card of the theme (the glass card is close to it)
        low = {k: round(cr(hexrgb(v), surf), 1) for k, v in tok.items() if k != "--card" and cr(hexrgb(v), surf) < 4.5}
        main = cr(hexrgb(tok["--tx"]), surf)
        chk(f"{th}: текст и цвета читаются на карточке (контраст ≥ 4.5), ниже порога: {low or 'нет'}", not low)
        chk(f"{th}: основной текст {main:.1f}:1 — не слепящие 21:1", 11 <= main <= 16.5)
        pg.click("#settingsBtn"); pg.wait_for_timeout(1500)
        if th == "dark":
            secs = pg.eval_on_selector_all("#settingsBody > .setSection", "els => els.map(e => e.textContent.trim())")
            chk(f"разделы настроек: {secs}", secs == ["Модули связки", "Торговля на бирже", "Уведомления", "Деньги и контроль", "Система", "Оформление", "Остальные модули"])
            gs = pg.eval_on_selector_all("#settingsBody > details.settingsGroup", "els => els.map(e => e.querySelector('summary').textContent.trim())")
            chk("модули связки первыми", gs[:6] == ["⚡ Лимитки 4ч+2ч", "P/R — Peak Reversal", "🧱 SMC", "📐 EMA — касания", "🔄 Классика наоборот", "📏 HTF-уровни"])
            three = pg.evaluate("""() => [...document.querySelectorAll('#settingsBody > details.settingsGroup')].slice(0, 6).map(g => {
                const rows = [...g.querySelectorAll('.settingRow')].filter(r => r.style.display !== 'none');
                return [!!rows[0].querySelector('input[id^="set"]'), rows[1].querySelector('input')?.dataset.mirror || '', rows[2].querySelector('input')?.dataset.mirror || '']; })""")
            chk(f"у каждого модуля связки три одинаковые строки (работа, торговля, уведомления): {three[0]}", all(t[0] and t[1].startswith("setAutotrade") and t[2].startswith(("setTg", "setTelegram")) for t in three))
            ids = pg.evaluate("[...document.querySelectorAll('#settingsBody [id]')].map(e => e.id)")
            chk(f"каждая настройка — один раз ({len(ids)} элементов с id)", len(ids) == len(set(ids)) and len(ids) > 100)
            miss = pg.evaluate("[...document.querySelectorAll('#settingsBody input[data-mirror]')].filter(m => !document.getElementById(m.dataset.mirror)).map(m => m.dataset.mirror)")
            chk("у каждого зеркала есть оригинал", not miss)
            tg = [g for g in gs if "Telegram" in g or "Сигналы" in g or "Сервисные" in g]
            where = pg.evaluate("""() => { const o = {}; for (const id of ['setTgDlm', 'setTelegramPrv', 'setTgSmc', 'setTelegramEmw', 'setTgCfl', 'setTgHtf', 'setTgTradeResults', 'setTelegramNetwork'])
                o[id] = document.getElementById(id).closest('details').querySelector('summary').textContent.trim(); return o; }""")
            chk(f"все уведомления — в разделе «Уведомления»: {sorted(set(where.values()))}", set(where.values()) <= set(tg))
            who = pg.evaluate("['Dlm','Prv','Smc','Emw','Cfl','Htf'].map(m => document.getElementById('setAutotrade' + m).closest('details').querySelector('summary').textContent.trim())")
            chk("кто торгует — в одной группе", set(who) == {"✅ Какие модули торгуют"})
            saved = []
            pg.on("request", lambda r: saved.append(r.post_data or "") if r.method == "POST" and "/api/settings" in r.url else None)
            st = pg.evaluate("""async () => {
                const m = document.querySelector('input[data-mirror="setTgSmc"]'), o = document.getElementById('setTgSmc');
                const a = [m.checked, o.checked]; m.click(); await new Promise(r => setTimeout(r, 900));
                const b = [m.checked, o.checked]; o.click(); await new Promise(r => setTimeout(r, 900));
                return [a, b, [m.checked, o.checked]]; }""")
            chk(f"зеркало и оригинал меняются вместе в обе стороны: {st}", st[0][0] == st[0][1] and st[1] == [not st[0][0]] * 2 and st[2] == st[0])
            chk(f"изменение через зеркало сохраняется (запросов сохранения {len(saved)})", len(saved) >= 2)
            pg.fill("#settingsSearch", "сторож"); pg.wait_for_timeout(400)
            vis = pg.eval_on_selector_all("#settingsBody > details.settingsGroup", "els => els.filter(x => !x.classList.contains('searchHidden') && x.style.display !== 'none').map(e => e.querySelector('summary').textContent.trim())")
            vsec = pg.eval_on_selector_all("#settingsBody > .setSection", "els => els.filter(x => !x.classList.contains('searchHidden')).map(e => e.textContent.trim())")
            chk(f"поиск находит группу по её названию; пустые разделы скрыты: {vsec}", any("Сторож" in g for g in vis) and "Оформление" not in vsec and "Деньги и контроль" in vsec)
            pg.fill("#settingsSearch", ""); pg.wait_for_timeout(300)
            sub = pg.evaluate("""() => { const s = document.querySelector('#setDlm').closest('.settingRow').querySelector('.sub'); s.closest('details').open = true;
                const h0 = s.getBoundingClientRect().height; s.click(); return [h0, s.getBoundingClientRect().height]; }""")
            chk(f"пояснение: две строки, по нажатию — целиком ({sub[0]:.0f} → {sub[1]:.0f} px)", sub[1] > sub[0] * 1.5)
        else:
            chk("день: холст графика — тёмная пластина", pg.evaluate("(() => { const c = document.createElement('canvas'); document.body.appendChild(c); const v = getComputedStyle(c).backgroundColor; c.remove(); return v; })()") in ("rgb(26, 27, 29)",))
            chk("график берёт ночные цвета и днём", pg.evaluate("getComputedStyle(document.getElementById('chartTokens')).getPropertyValue('--tx').trim()") == "#e6e7e8")
            pg.evaluate("document.getElementById('setTheme').closest('details').open = true"); pg.wait_for_timeout(200)
            pg.select_option("#setTheme", "dark"); pg.wait_for_timeout(300)
            chk("тема закреплена в настройках — «Ночь» при светлой теме телефона", pg.evaluate("document.documentElement.getAttribute('data-theme')") == "dark")
            pg.reload(); pg.wait_for_timeout(2500)
            chk("…и держится после перезагрузки страницы", pg.evaluate("document.documentElement.getAttribute('data-theme')") == "dark" and pg.evaluate("document.getElementById('setTheme').value") == "dark")
            pg.evaluate("setTheme('auto')"); chk("«Авто» — снова как в телефоне", pg.evaluate("document.documentElement.getAttribute('data-theme')") == "light")
        chk(f"{th}: ошибок на странице нет {errs}", not errs)
        pg.close()
    b.close()
print("t_design793 OK" if ok else "t_design793 FAIL")
