"""v0.99.766 — the universal liquidity cut: the steps parsed (bad ones refused), the slope continuous and monotone, every real
position sized by compute_risk_based_position cut by its share of the coin's hourly turnover (a small one untouched, a large one
to the cap; off / no turnover -> untouched), the settings (the empty field = the version's default, a typed one kept, a bad one
refused), /api/liq, the settings' group in the page"""
import os, sys, time, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import V
ok = True
def chk(nm, c):
    global ok
    print(f"{nm}: {'да' if c else 'НЕТ'}"); ok &= bool(c)
st = V.liq_steps_parse("2:0.5/4:0.25/8:0")
chk("разбор шагов", st == [(0.02, 0.5), (0.04, 0.25), (0.08, 0.0)] and V.liq_steps_parse("5:0") == [(0.05, 0.0)] and V.liq_steps_parse("2%:0.5, 4:0") == [(0.02, 0.5), (0.04, 0.0)])
bad = 0
for x in ("4:0/2:0", "2:1.5", "2:0.2/4:0.5", "x", "0:0"):
    try: V.liq_steps_parse(x)
    except Exception: bad += 1
chk("плохие шаги отклонены", bad == 5)
ps = [i / 1000 for i in range(0, 200)]; g = [V.liq_g(p, st) for p in ps]
chk("кривая непрерывна и не убывает", all(b >= a - 1e-12 for a, b in zip(g, g[1:])) and abs(V.liq_g(0.02, st) - 0.02) < 1e-12 and abs(V.liq_g(0.08, st) - 0.04) < 1e-12 and abs(V.liq_g(0.5, st) - 0.04) < 1e-12)
TURN = {"SOL_USDT": 50e6, "TINY_USDT": 100_000.0}
V.liq_turnover = lambda sym, now=None: TURN.get(sym if "_" in sym else sym[:-4] + "_USDT")
V.LIQ_STEPS = ""; V.LIQ_ENABLED = True
def notional(sym, eq, risk=4.0):
    m, lev, skip = V.compute_risk_based_position("LONG", 1.0, 0.96, 20, 0.5, eq, risk_pct=risk, symbol=sym)
    return m * lev
n_small = notional("TINY_USDT", 230)
n_big = notional("TINY_USDT", 100_000)
n_sol = notional("SOL_USDT", 100_000)
n_bn = notional("TINYUSDT", 100_000)   # Binance's name (bn_size passes it)
V.LIQ_ENABLED = False; n_off = notional("TINY_USDT", 100_000); V.LIQ_ENABLED = True
n_none = notional("NOPE_USDT", 100_000)
print(f"  позиция $230 на тонкой монете {n_small:,.0f} · $100k на тонкой {n_big:,.0f} (оборот $100k/ч) · на SOL {n_sol:,.0f} · выключено {n_off:,.0f} · без оборота {n_none:,.0f}")
chk("маленький счёт не урезается", abs(n_small - 230 * 0.04 / (0.04 + 2 * V.SCALP_TAKER_FEE_PCT)) < 1e-6 * n_small)
chk("крупная позиция на тонкой монете — 7% оборота (по умолчанию 4:0.5/8:0.25/12:0)", abs(n_big - 7000) < 1e-6 and abs(n_bn - 7000) < 1e-6)
chk("на ликвидной монете не урезается", abs(n_sol - n_off) < 1e-6 * n_sol and n_off > 90_000)
chk("выключено / нет оборота — без урезания", abs(n_none - n_off) < 1e-6 * n_off)
V.apply_settings({"liq_steps": "2:0.5/4:0.25/8:0"}); n2 = notional("TINY_USDT", 100_000)
chk("свои шаги: позиция = 4% оборота (2% + 2%×0.5 + 4%×0.25)", V.LIQ_STEPS == "2:0.5/4:0.25/8:0" and abs(n2 - 4000) < 1e-6)
V.apply_settings({"liq_steps": "4:0/2:0"}); chk("плохие шаги в настройках не приняты", V.LIQ_STEPS == "2:0.5/4:0.25/8:0")
V.apply_settings({"liq_steps": ""}); chk("пустое поле = шаги версии", V.LIQ_STEPS == "" and V.liq_steps_now() == V.LIQ_STEPS_DEFAULT)
V.apply_settings({"liq_enabled": False}); chk("выключатель", V.LIQ_ENABLED is False and V.get_settings()["liq_enabled"] is False); V.apply_settings({"liq_enabled": True})
d = V.app.test_client().get("/api/liq", environ_base={"REMOTE_ADDR": "127.0.0.1"}).get_json()
chk("/api/liq: урезания записаны", d["enabled"] and d["steps"] == V.LIQ_STEPS_DEFAULT and any(c["symbol"] in ("TINY_USDT", "TINYUSDT") and c["kept"] < 1 for c in d["cuts"]))
threading.Thread(target=lambda: V.app.run(port=5111, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium"); pg = b.new_page(viewport={"width": 420, "height": 900})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:5111/"); pg.wait_for_timeout(3000); pg.click("#settingsBtn"); pg.wait_for_timeout(1500)
    txt = pg.locator("#liqRecent").text_content(); ph = pg.locator("#setLiqSteps").get_attribute("placeholder")
    chk("группа в настройках, последние урезания видны", "последние урезания" in txt and "TINY" in txt and ph == "по умолчанию" and pg.locator("#setLiqEnabled").is_checked())
    chk("нет ошибок страницы", not errs); b.close()
print("t_liq OK" if ok else "t_liq FAIL"); sys.exit(0 if ok else 1)
