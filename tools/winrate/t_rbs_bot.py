"""v0.99.757 — 🚀 Пробой 4ч in the bot against the research (rb_short.py / rbs_feat.py / rbs_export.py): on the lab's 4h
bars of real coins (the bot's 1500-bar look) the bot finds the research's breakouts and no others, its 31 features match
the research's rows, its score matches the model's; the scan opens the virtual trade at the next 4h open with the stop
1.5 ATR / the take 2R, the settle closes it as the research's walk (the R with the fees); the tab, the backtest list, the
settings, no page errors"""
import os, sys, time, threading, numpy as np
from common import V
sys.argv = ["x", "4"]
import rbs_feat as RF
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
res = {}
m = V.rbs_model()
res["model loads (feats, rule)"] = bool(m) and m["feats"] == V.RBS_FNAMES and m["rule"]["thr"] == 0.8 and len(m["coins"]) >= 120
z = dict(np.load(f"{ST}/wf/rbs_4.npz")); X = np.load(f"{ST}/wf/rbs_4_X.npz")["X"]
SI, XI, HI = 1, 0, 1   # stop 1.5, t2, 2 days (rb_short's grid)
bars = {s: RF.load(s) for s in ("BTCUSDT", "SOLUSDT", "DOGEUSDT", "LINKUSDT", "1000PEPEUSDT", "ARBUSDT")}


def window(sym, t_close, n=V.RBS_W4):
    T, O, H, L, C, Vv = bars[sym]
    k = int(np.searchsorted(T + 14400, t_close, side="right"))
    a = max(0, k - n)
    return [list(map(float, x[a:k])) for x in (T, O, H, L, C, Vv)]


rng = np.random.default_rng(3)
fd, sd, miss, extra, nev, nbar = [], [], 0, 0, 0, 0
for sym in ("SOLUSDT", "DOGEUSDT", "LINKUSDT", "1000PEPEUSDT", "ARBUSDT"):
    ks = np.flatnonzero((z["sym"] == sym) & (z["t"] > 1.70e9))
    for k in rng.choice(ks, min(25, len(ks)), replace=False):
        t = float(z["t"][k]); T, O, H, L, C, Vv = window(sym, t)
        if not T or T[-1] + 14400 != t:
            continue
        bT, bO, bH, bL, bC, bV = window("BTCUSDT", t); bi = V.rbs_ind(bO, bH, bL, bC, bV)
        B = {"T": bT, "C": bC, "e200": bi["e200"], "atr": bi["atr"]}
        ind = V.rbs_ind(O, H, L, C, Vv); i = len(C) - 1
        ev = {(s, N): (rg, brk) for s, N, rg, brk in V.rbs_events_at(ind, H, L, C, i, m["rule"])}
        key = (int(z["side"][k]), int(z["N"][k])); nev += 1
        if key not in ev:
            miss += 1; continue
        f = V.rbs_features(T, O, H, L, C, Vv, ind, i, key[0], key[1], *ev[key], B)
        x = X[k].astype(float)
        fd.append(np.max(np.abs(np.array(f) - x) / np.maximum(1.0, np.abs(x))))
        sd.append(abs(V.rbs_score(m, f) - V.rbs_score(m, [float(v) for v in x])))
    # bars with no research event: the bot finds none either
    T_all = bars[sym][0]; evt = set(int(v) for v in z["t"][z["sym"] == sym])
    for j in rng.choice(np.arange(2000, len(T_all) - 1), 40, replace=False):
        t = float(T_all[j] + 14400)
        if int(t) in evt:
            continue
        T, O, H, L, C, Vv = window(sym, t); ind = V.rbs_ind(O, H, L, C, Vv); nbar += 1
        extra += bool(V.rbs_events_at(ind, H, L, C, len(C) - 1, m["rule"]))
print(f"   events {nev}, missed {miss}; no-event bars {nbar}, extra {extra}; features max rel diff {max(fd):.2e}; score max diff {max(sd):.2e}")
res["the research's breakouts found, no others"] = miss == 0 and extra == 0 and nev >= 80
res["31 features as the research's rows"] = max(fd) < 5e-3   # the 1000-bar look: EMA200 within ~0.2%, the score the same
res["the score as on the research's row"] = max(sd) < 1e-3

# the scan -> the trade -> the settle, on a coin's real bars (cfl_klines faked from the lab's)
cand = [k for k in np.flatnonzero(np.isin(z["sym"], ["SOLUSDT", "DOGEUSDT", "LINKUSDT", "ARBUSDT"]) & (z["t"] > 1.72e9) & np.isfinite(z["y"][:, SI, XI, HI, 0]))
        if V.rbs_score(m, [float(v) for v in X[k]]) > 0.8][:3]
NOW = {"t": 0}


def fake_klines(bsym, interval, n):
    T, O, H, L, C, Vv = bars.get(bsym) or bars["SOLUSDT"]
    k = int(np.searchsorted(T, NOW["t"], side="right"))   # the bars that started by now (the forming one too)
    a = max(0, k - n)
    return [list(map(float, x[a:k])) for x in (T, O, H, L, C, Vv)]


_time, _sleep = time.time, time.sleep   # V.time is this very module: patched for the scan, restored after
V.cfl_klines = fake_klines; V.rbs_save = lambda: None; time.sleep = lambda s: None; V.send_telegram = lambda *a, **k: None
done = []
V.notify_trade_result = lambda *a, **k: done.append(a)
ok_scan, ok_settle = [], []
for k in cand:
    sym = str(z["sym"][k]); t = float(z["t"][k])
    V._RBS["trades"] = []
    m_ = dict(m, coins=[sym]); V._RBS["model"] = m_
    NOW["t"] = t + 120; time.time = lambda: NOW["t"]
    V.rbs_scan(int(t))
    tr = V._RBS["trades"][0] if V._RBS["trades"] else {}
    e = float(z["e"][k]); risk = 1.5 * float(z["atr"][k]); s = int(z["side"][k])
    ok_scan.append(bool(tr) and abs(tr["entry"] - e) < 1e-9 * e and abs(tr["sl"] - (e - s * risk)) < 1e-6 * e and abs(tr["tp"] - (e + s * 2 * risk)) < 1e-6 * e)
    NOW["t"] = t + 13 * 14400 + 100
    V.rbs_settle(NOW["t"])
    rr = V._RBS["trades"][0].get("r") if V._RBS["trades"] else None
    ok_settle.append(rr is not None and abs(rr - float(z["y"][k, SI, XI, HI, 0])) < 2e-3)
    print(f"   {sym} {s:+d} N{int(z['N'][k])}: entry {tr.get('entry')} vs {e}; R {rr} vs the research {float(z['y'][k, SI, XI, HI, 0]):+.3f} ({(V._RBS['trades'][0] if V._RBS['trades'] else {}).get('result')})")
time.time, time.sleep = _time, _sleep
res["the scan opens at the next 4h open, stop 1.5 ATR, take 2R"] = len(ok_scan) >= 2 and all(ok_scan)
res["the settle closes as the research (R with the fees)"] = len(ok_settle) >= 2 and all(ok_settle) and len(done) == len(ok_settle)
# one trade a coin at a time
V._RBS["trades"] = [{"bsym": "SOLUSDT", "status": "OPEN", "id": "x"}]
res["one trade a coin"] = V.rbs_open({"bsym": "SOLUSDT", "side": 1, "N": 20, "score": 1.0, "atr": 1.0, "close": 100.0, "fill": 100.0}, 1, m) is False
V._RBS["trades"] = []

# the tab, the backtest list, the settings, no page errors
V._RBS["model"] = m
V._RBS["scan"] = {"t": int(time.time()), "bar": int(time.time()) // 14400 * 14400, "coins": 127, "events": 9, "thr": 0.8, "cands": 1, "opened": 1, "errs": 0,
                  "near": [{"symbol": "SOL_USDT", "side": 1, "N": 30, "score": 0.93}]}
V._RBS["trades"] = [{"id": "a", "symbol": "SOL_USDT", "bsym": "SOLUSDT", "scl": 1.0, "side": 1, "direction": "LONG", "N": 30, "score": 0.93, "atr_bn": 2.0,
                     "t_in": int(time.time()) // 14400 * 14400, "hold": 12, "until": int(time.time()) + 86400, "status": "OPEN", "entry": 150.0, "sl": 147.0, "tp": 156.0,
                     "result": None, "r": None, "exit": None, "t_out": None, "real": False, "rv": 1},
                    {"id": "b", "symbol": "DOGE_USDT", "bsym": "DOGEUSDT", "scl": 1.0, "side": -1, "direction": "SHORT", "N": 20, "score": 0.85, "atr_bn": 0.002,
                     "t_in": int(time.time()) - 5 * 86400, "hold": 12, "until": int(time.time()) - 3 * 86400, "status": "CLOSED", "entry": 0.2, "sl": 0.203, "tp": 0.194,
                     "result": "WIN", "r": 1.93, "exit": 0.194, "t_out": int(time.time()) - 4 * 86400, "real": False, "rv": 1}]
st = V.app.test_client().get("/api/rbs/status").get_json()
bt = V.app.test_client().get("/api/bt/trades?mod=rbs").get_json()["trades"]
res["status + backtest list"] = st["n"] == 1 and st["open"][0]["symbol"] == "SOL_USDT" and len(bt) > 800 and all(t["c"] == "4h" and t.get("n") for t in bt)
V.apply_settings({"rbs_enabled": False, "telegram_alerts_rbs": False}); off = (V.RBS_ENABLED, V.TELEGRAM_ALERTS_RBS)
V.apply_settings({"rbs_enabled": True, "telegram_alerts_rbs": True})
res["settings"] = off == (False, False) and V.RBS_ENABLED and V.get_settings().get("rbs_enabled") is True
threading.Thread(target=lambda: V.app.run(port=5111, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium"); pg = b.new_page(viewport={"width": 420, "height": 900})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:5111/"); pg.wait_for_timeout(3000)
    pg.click('.tab[data-tab="rbs"]'); pg.wait_for_timeout(3000)
    pg.click("#rbsPanel details.zcard summary >> text=Сделки бэктеста"); pg.wait_for_timeout(2500)
    txt = pg.locator("#rbsPanel").inner_text()
    pg.screenshot(path="ui_rbs.png", full_page=True)
    res["the tab"] = ("Пробой 4ч" in txt and "виртуально" in txt and "SOL" in txt and "коридор 30" in txt and "2025" in txt and "845 сделок" in txt)
    if not res["the tab"]: print(txt[:2500])
    pg.locator("#rbsPanel div[onclick^=\"btOpen('rbs'\"]").first.click(); pg.wait_for_timeout(3000)
    pg.screenshot(path="ui_rbs_chart.png")
    res["a backtest trade's chart"] = "Пробой 4ч" in pg.locator("#vgiModalTitle").inner_text()
    res["no page errors"] = not errs
    if errs: print(errs)
    b.close()
print(" · ".join(f"{k} {v}" for k, v in res.items()))
ok = all(res.values()); print("ALL OK" if ok else "FAILED"); sys.exit(0 if ok else 1)
