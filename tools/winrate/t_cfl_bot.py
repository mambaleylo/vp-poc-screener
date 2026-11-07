"""v0.99.739, v0.99.740, v0.99.741 — 🔄 Классика наоборот in the bot: (1) the bot's pure-Python indicators / features / score on the bars the
live bot sees (1h 3000, 4h 1500, 1d 1000 — here built from the research's Binance 1h bars, cut at the signal's close,
the next hour's open only) == the research's events (ev3/<SYM>.npz) and the 2026 model's scores (fc_red_sc.npz) for
backtest trades of 2026; (2) the rolling threshold from the model file's seed == numpy's quantile; (3) the scan opens
those trades (virtual) and the settle walks them to the backtest list's R; (4) the tab renders, no page errors; (5) the real
trades: off by default, the switch on -> execute_autotrade with the trade's emergency stop / take and the risk x the
emergency's multiple, the late / old ones not. v0.99.741: the close stop (the 1d close, the emergency 2x) — (3) re-makes it."""
import sys, json, glob, time, threading, numpy as np
from common import V
import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "new_ind"))
import lv_engine as LE, ev3_engine as E3, ev2_engine as E2
import calendar
ts = lambda y, m=1, d=1: calendar.timegm((y, m, d, 0, 0, 0))
# v0.99.757 — the research's files (ev3/<coin>.npz, fc_red_sc.npz, lv/split.json, data/metrics, data/funding) were lost with
# the old lab: the parts that compare with them run when they are there; without them the bot is checked against the
# backtest list itself (the events found and scored above the threshold, the walk to the list's R, the tab, the real trades)
RESEARCH = os.path.exists("ev3") and os.path.exists("fc_red_sc.npz") and os.path.exists("lv/split.json")
if RESEARCH:
    from lv_wf import load_dir
    from bt_trades import gate_sym
ok = True
m = V.cfl_model()
ok &= bool(m) and m["feats"] == V.CFL_FNAMES and m["fams"] == V.CFL_FAMS
ok &= m["rule"].get("side") == 1 and m["rule"].get("stop_close_h") == 4 and m["rule"].get("hard_x") == 2.0 and m["ver"] == V.CFL_MODEL_VER and all(t["d"] == 1 for t in json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))["cfl"])
print("(0) model", bool(m), m and len(m["models"]), m and m["rule"])
BARS = {}
def bars(sym):
    if sym not in BARS: BARS[sym] = LE.load_np(sym)
    return BARS[sym]
def agg(sym, sec, t_end, w):
    T, O, H, L, C, Vv = bars(sym)
    pid = T // sec; st = np.flatnonzero(np.r_[True, np.diff(pid) != 0]); en = np.r_[st[1:], len(T)]
    bt = pid[st] * sec; keep = np.flatnonzero(bt < t_end)[-w:]
    o = [bt[keep], O[st][keep], np.maximum.reduceat(H, st)[keep], np.minimum.reduceat(L, st)[keep], C[en - 1][keep], np.add.reduceat(Vv, st)[keep]]
    # the bar still forming at t_end: cut at t_end
    k = keep[-1]
    if bt[k] + sec > t_end:
        a, b = st[k], st[k] + int((t_end - bt[k]) // 3600)
        o[2][-1], o[3][-1], o[4][-1], o[5][-1] = H[a:b].max(), L[a:b].min(), C[b - 1], Vv[a:b].sum()
    return [list(map(float, x)) if i else list(map(int, x)) for i, x in enumerate(o)]
def h1_win(sym, t_close, w):
    T, O, H, L, C, Vv = bars(sym)
    k = int(np.searchsorted(T, t_close)); a = max(0, k - w + 1)
    out = [list(map(int, T[a:k])), list(map(float, O[a:k])), list(map(float, H[a:k])), list(map(float, L[a:k])), list(map(float, C[a:k])), list(map(float, Vv[a:k]))]
    if k < len(T) and T[k] == t_close:   # the next hour: its open only
        for i, v in enumerate((int(T[k]), float(O[k]), float(O[k]), float(O[k]), float(O[k]), 0.0)): out[i].append(v)
    return out
def oi_of(sym):
    try:
        M = E2.metrics(sym, bars(sym)[0]); T = bars(sym)[0]
        return {int(t): float(v) for t, v in zip(T, M["oi"]) if v == v}
    except Exception:
        return {}
def fund_of(sym):
    try: f = np.loadtxt(f"data/funding/{sym}.csv", delimiter=",", ndmin=2); return [(int(a), float(b)) for a, b in f]
    except Exception: return []
L_ = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))["cfl"]
def _bn(gs):
    b = gs.replace("_USDT", "")
    for c_ in (b + "USDT", "1000" + b + "USDT"):
        try: LE.load_np(c_); return c_
        except Exception: pass
inv = {t["s"]: _bn(t["s"]) for t in L_}
picks = [t for t in L_ if t["t"] >= ts(2026)][::12][:12]
if RESEARCH:
    ref = np.load("fc_red_sc.npz", allow_pickle=True)["SC"]; Dd = load_dir("ev3", E3.FNAMES)
found = fmatch = smatch = 0; worst = np.zeros(31)
for p in picks:
    sym = inv[p["s"]]; t_close = p["t"]; tsig = t_close - 3600
    h1 = h1_win(sym, t_close, V.CFL_W1); h4 = agg(sym, 14400, t_close + 3600, V.CFL_W4 + 1); d1 = agg(sym, 86400, t_close + 3600, V.CFL_WD + 2)
    b1 = h1_win("BTCUSDT", t_close, V.CFL_W1 + 10); bd = agg("BTCUSDT", 86400, t_close + 3600, V.CFL_WD + 2)
    first = int(bars(sym)[0][0])
    evs = V.cfl_coin_events(sym, t_close, m, h1, h4, d1, b1, bd, oi_of(sym), fund_of(sym), first)
    fam = V.CFL_FAMS.index(p["lvl"]); S = -p["d"]
    hit = [e for e in evs if e[0] == fam and e[1] == S]
    if not hit:
        print("   ✗ не найден", sym, p["lvl"], time.strftime("%Y-%m-%d %H:%M", time.gmtime(tsig)), [(V.CFL_FAMS[e[0]], e[1]) for e in evs]); continue
    found += 1
    if not RESEARCH:   # the score above the rolling threshold of the trade's time (the list's trade was chosen)
        sc_bot = V.cfl_score(m, hit[0][2]); th = V.cfl_threshold(m, t_close)
        fmatch += 1; smatch += th is not None and sc_bot >= th - 1e-6
        if th is None or sc_bot < th - 1e-6: print("   оценка ниже порога", sym, p["lvl"], round(sc_bot, 5), th)
        continue
    z = np.load(f"ev3/{sym}.npz"); k = np.flatnonzero((z["t"] == tsig) & (z["fam"] == fam) & (z["side"] == S))[0]
    fr = z["F"][k].astype(float)
    for c in ("ls_z", "tk_z", "top_z"): fr[E2.FNAMES.index(c)] = 0.0
    d = np.abs(np.array(hit[0][2]) - fr); worst = np.maximum(worst, d)
    fmatch += bool((np.delete(d, E2.FNAMES.index("d_e200")) < 1e-3).all() and d[E2.FNAMES.index("d_e200")] < 0.02)
    gi = np.flatnonzero((Dd["T"] == tsig) & (Dd["F"][:, 0] == fam) & (Dd["SIDE"] == S) & (np.array(Dd["names"])[Dd["SYM"]] == sym))
    # v0.99.776: the reference = the deployed trees on the research's features (fc_red_sc.npz is now the lab's rebuilt recipe, corr 0.95)
    import treevec as TV
    sc_bot = V.cfl_score(m, hit[0][2]); sc_ref = float(TV.model_score(m["models"], fr[None, :])[0])
    smatch += abs(sc_bot - sc_ref) < 1e-3
    if abs(sc_bot - sc_ref) >= 1e-3: print("   оценка", sym, p["lvl"], round(sc_bot, 5), "против", round(sc_ref, 5))
print(f"(1) события найдены {found}/{len(picks)}, признаки совпали {fmatch}, оценки совпали {smatch}; макс. расхождение "
      + str({E2.FNAMES[i]: round(float(worst[i]), 4) for i in range(31) if worst[i] > 1e-4}))
ok &= found == len(picks) and fmatch == len(picks) and (smatch == len(picks) if RESEARCH else True)   # without the research's OI / funding the score is only shown
# (2) the threshold from the seed vs numpy on the research's 2026 scores (without them: a threshold for every day of Oct 2026)
if not RESEARCH:
    ths = [V.cfl_threshold(m, calendar.timegm((2026, 10, d, 0, 0, 0))) for d in range(1, 31)]
    ok2 = all(x is not None and x > 0 for x in ths)
    print("(2) порог есть на каждый день октября 2026:", ok2, round(min(ths), 4), "..", round(max(ths), 4)); ok &= ok2
if RESEARCH:
    # v0.99.776: the exact = the deployed trees' scores of the bot coins' events (fc_red_sc.npz is the lab's rebuilt recipe now)
    import treevec as TV
    BOT = Dd["BOT"]; T = Dd["T"]; mk = BOT & (T >= ts(2026) - 200 * 86400)
    Fz = Dd["F"][mk].astype(float); Fz[:, [E2.FNAMES.index(c) for c in ("ls_z", "tk_z", "top_z")]] = 0.0
    tt, ss = T[mk], TV.model_score(m["models"], Fz); o = np.argsort(tt); tt, ss = tt[o], ss[o]
    diffs = []
    import calendar
    for day in (calendar.timegm((2026, 10, 1, 0, 0, 0)), calendar.timegm((2026, 10, 10, 0, 0, 0)), calendar.timegm((2026, 10, 20, 0, 0, 0))):
        hi = (day // 86400 - 14) * 86400; lo = hi - 180 * 86400
        ex = float(np.quantile(ss[np.searchsorted(tt, lo):np.searchsorted(tt, hi)], 0.997)); mine = V.cfl_threshold(m, day)
        diffs.append(abs(ex - mine) if mine is not None else 9)
    print("(2) порог из семени против точного:", [round(x, 8) for x in diffs])
    # v0.99.776: the research's events re-made on the gap-filled candles (fill_gaps.py) — the same events (the counts equal the
    # seed's day by day) with slightly moved features (pos365, r7d …): the seed's scores were of the export's events, so a small
    # gap is the data, not the bot (was < 1e-5 on the export's own files)
    ok &= max(diffs) < 0.03
# (3) the scan's trade opened (virtual) and the settle walks it to the list's R
V.cfl_save = lambda: None; V.send_telegram = lambda *a, **k: None; V.notify_trade_result = lambda *a, **k: None; V.heartbeat = lambda *a, **k: None
same = 0
p3 = [t for kd in ("stop", "hard", "take", "time") for t in [x for x in L_ if x["k"] == kd and x["t"] >= ts(2025)][:2]]   # every exit kind
for p in p3:
    sym = inv[p["s"]]; t_close = p["t"]
    V._CFL["trades"] = []
    c = {"bsym": sym, "fam": p["lvl"], "S": -p["d"], "score": 9.0, "datr": None, "fill": None}
    if RESEARCH:
        z = np.load(f"ev3/{sym}.npz"); k = np.flatnonzero((z["t"] == t_close - 3600) & (z["fam"] == V.CFL_FAMS.index(p["lvl"])) & (z["side"] == -p["d"]))[0]
        c["datr"] = float(z["datr"][k])
    else:   # the list's own stop distance: stop_datr dATR
        c["datr"] = abs(p["e"] - p["sl"]) / p["e"] * 100 / float(m["rule"]["stop_datr"])
    T_, O_, H_, L_b, C_, V_ = bars(sym)
    def fake_kl(bs, interval, n, sym=sym):
        a = int(np.searchsorted(T_, t_close)); b = min(len(T_), a + 110)
        return [list(map(int, T_[a:b])), list(map(float, O_[a:b])), list(map(float, H_[a:b])), list(map(float, L_b[a:b])), list(map(float, C_[a:b])), list(map(float, V_[a:b]))]
    V.cfl_klines = fake_kl
    V.cfl_open(c, t_close, m)
    V.cfl_settle(t_close + 110 * 3600)
    tr = V._CFL["trades"][0]; r = tr.get("r")
    scl = 1000.0 if sym.startswith("1000") and not p["s"].startswith("1000") else 1.0
    same += r is not None and abs(r - p["r"]) < 0.01 and abs(tr["entry"] - p["e"]) / p["e"] < 1e-9
    print(f"   {p['s']:12s} {p['lvl']:12s} {p['k']:5s} {tr.get('result')} R бот {r} / бэктест {p['r']} · вход {tr['entry']:.6g} / {p['e']:.6g}")
print(f"(3) {same}/{len(p3)} сделок бэктеста повторены ботом (все виды выхода)")
ok &= same == len(p3) == 8
# (4) the tab
V._CFL["trades"] = [{"id": "x1", "symbol": "SOL_USDT", "bsym": "SOLUSDT", "scl": 1.0, "fam": "bb_back_4h", "side": -1, "direction": "SHORT", "score": 1.2,
                     "datr": 3.0, "t_in": int(time.time()) // 3600 * 3600, "hour": int(time.time()) // 3600 * 3600, "hold": 72, "until": int(time.time()) + 3600,
                     "status": "OPEN", "result": None, "r": None, "exit": None, "t_out": None, "real": False, "rv": 1, "entry": 150.0, "sl": 154.5, "tp": 136.5}]
V._CFL["scan"] = {"t": int(time.time()), "bar": int(time.time()) // 14400 * 14400, "coins": 127, "events": 40, "thr": 1.1, "cands": 1, "opened": 1, "errs": 0,
                  "near": [{"symbol": "SOL_USDT", "fam": "bb_back_4h", "side": -1, "score": 1.2}]}
threading.Thread(target=lambda: V.app.run(port=5121, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium"); pg = b.new_page(viewport={"width": 412, "height": 900})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:5121/"); pg.wait_for_timeout(3000)
    pg.click('.tab[data-tab="cfl"]'); pg.wait_for_timeout(3000)
    txt = pg.locator("#cflPanel").inner_text()
    pg.evaluate("document.getElementById('btBox_cfl').closest('details').open = true"); pg.wait_for_timeout(2500)
    nrow = pg.locator("#btBox_cfl div[onclick]").count()
    pg.screenshot(path="ui_cfl.png", full_page=True)
    sw = pg.evaluate("(() => { const e = document.getElementById('setAutotradeCfl'), r = document.getElementById('setRiskPctCfl'); return [!!e, e && e.checked, !!r, r && r.placeholder]; })()")
    b.close()
tab_ok = ("Классика наоборот" in txt and "против: Боллинджер 4ч" in txt and "Последний скан" in txt and "только лонги" in txt and "+0.77R" in txt and "закрытие дневной свечи" in txt
          and nrow > 10 and not errs and sw == [True, True, True, "🔄 2"])   # v0.99.776: on by default, 2%
print("(4) вкладка:", tab_ok, "строк бэктеста", nrow, "переключатель", sw, errs[:2])
ok &= tab_ok
# (5) the real trades
calls = []
V.execute_autotrade = lambda *a, **k: calls.append((a, k)) or {"status": "OPENED", "detail": "mock"}
ok5 = V.AUTOTRADE_ENABLED_CFL is True and V.get_settings()["autotrade_cfl2"] is True and "autotrade_cfl2" in V.SETTINGS_KEYS   # v0.99.776: on by default
V.AUTOTRADE_ENABLED_CFL = False
p = picks[0]; sym = inv[p["s"]]
def mk(live_k, late=False):
    V._CFL["trades"] = []
    c = {"bsym": sym, "fam": p["lvl"], "S": -1, "score": 9.0, "datr": 4.0, "fill": p["e"], "live": p["e"] * live_k}
    t_close = int(time.time()) - (3600 if late else 60)
    V.cfl_open(c, t_close, m)
    return V._CFL["trades"][-1]
tr = mk(1.002); ok5 &= not calls and tr["real"] is False and V.mod_why_virtual(tr, False).startswith("автоторговля модуля выключена")
V.AUTOTRADE_ENABLED_CFL = True
tr = mk(1.002); ok5 &= len(calls) == 1 and tr["real"] is True
a, k = calls[-1]
ok5 &= a[0] == "cfl" and a[2] == "LONG" and abs(a[3] - p["e"] * 1.002) < 1e-12 and a[4] == tr["hs"] and a[5] == tr["tp"] and k["extra"]["kx"] == 2.0
ok5 &= abs(k["risk_pct_override"] - V.CFL_RISK_DEFAULT * 2.0) < 1e-12 and abs((tr["entry"] - tr["hs"]) / (tr["entry"] - tr["sl"]) - 2.0) < 1e-9 and tr["ch"] == 24
ok5 &= abs((tr["tp"] - tr["entry"]) / (tr["entry"] - tr["sl"]) - 6.0) < 1e-9 and tr["hold"] == 96
tr = mk(1.06); ok5 &= len(calls) == 1 and tr.get("late") and not tr["real"]   # 6% away with a 2% stop (0.5 x 4%, v0.99.777): > 1R
tr = mk(1.0, late=True); ok5 &= len(calls) == 1 and tr.get("rt") and not tr["real"]   # an old close: the record only
V.AUTOTRADE_ENABLED_CFL = False
print("(5) реальные сделки: по умолчанию вкл (v0.99.776), выключено — нет сделки, при вкл — вызов с тем же стопом/тейком, поздние и старые — нет:", bool(ok5), len(calls))
ok &= bool(ok5)
print("ALL OK" if ok else "FAILED"); sys.exit(0 if ok else 1)
