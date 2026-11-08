"""v0.99.783 — the user: "подними блоки сейчас и сделки вверх первыми под шапку": on every module's tab the «🔎 …» and «📈 Сделки» cards
come first, their own order kept; the rest below in its order; a synthetic panel too (the lift is in the panels' common setter)"""
import time, threading
from common import V
ok = True
def chk(nm, c):
    global ok
    print(("OK  " if c else "FAIL") + " " + nm); ok &= bool(c)
threading.Thread(target=lambda: V.app.run(port=5151, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium"); pg = b.new_page(viewport={"width": 412, "height": 900}, device_scale_factor=2)
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:5151/"); pg.wait_for_timeout(4000)
    for tab, panel in (("dlm", "dlmPanel"), ("prv", "prvPanel"), ("smc", "smcPanel"), ("emw", "emwPanel"), ("cfl", "cflPanel"), ("htf", "htfPanel")):
        if not pg.locator(f'.tab[data-tab="{tab}"]').count(): continue
        pg.click(f'.tab[data-tab="{tab}"]'); pg.wait_for_timeout(3500)
        hs = pg.evaluate(f"""(() => {{ const p = document.getElementById('{panel}'); if (!p) return null; const r = p.querySelector(':scope > .fx-zpanel') || p;
            return [...r.children].filter(c => c.classList.contains('zcard')).map(c => ((c.querySelector(':scope > .zh') || {{}}).textContent || '').trim().slice(0, 22)); }})()""")
        if hs is None: print("   нет панели", panel); continue
        now_ = [h for h in hs if h.startswith("🔎") or h.startswith("🎯 На прицеле")]; tr_ = [h for h in hs if h.startswith("📈 Сделки")]
        chk(f"{tab}: первыми {hs[:len(now_) + len(tr_)]} (всего карточек {len(hs)})", hs[:len(now_) + len(tr_)] == now_ + tr_ and len(now_) >= 1 and len(tr_) >= 1)
        if tab == "dlm": pg.screenshot(path="/tmp/claude-0/lift_dlm.png", clip={"x": 0, "y": 0, "width": 412, "height": 900})
    # a synthetic panel: the order of the rest kept
    got = pg.evaluate("""(() => { const p = document.getElementById('dlmPanel');
        p.innerHTML = '<div class="fx-zpanel"><div class="dim">описание</div><div class="zcard"><div class="zh">📊 История</div></div><div class="zcard"><div class="zh">🔎 Сейчас</div></div><div class="zcard"><div class="zh">📈 Сделки</div></div><div class="zcard"><div class="zh">💰 Деньги</div></div></div>';
        return [...p.querySelector('.fx-zpanel').children].map(c => c.textContent.trim()); })()""")
    chk(f"порядок: {got}", got == ["🔎 Сейчас", "📈 Сделки", "описание", "📊 История", "💰 Деньги"])
    chk("без ошибок JS", not errs)
    b.close()
print("t_lift OK" if ok else "t_lift FAIL")
