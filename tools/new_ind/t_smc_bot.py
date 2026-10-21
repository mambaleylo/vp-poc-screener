"""v0.99.678 — 🧱 SMC in the bot: (1) the bot's pure-Python levels / features == the research engine's (lv2 npz) on
Binance bars; (2) the model file loads, its features / families match the code; (3) at the hour of backtest trades
the bot arms that level (candles mocked from Binance history) and a touch opens the trade, the settle walks it to the
same result as the backtest list; (4) the risk fields are number fields (saved as numbers)."""
import sys, bisect, json, time, numpy as np
from common import V
import lv_engine as LE
ok = True
def bars(sym):
    T, O, H, L, C, Vv = LE.load_np(sym)
    return [{"time": int(t), "open": o, "high": h, "low": l, "close": c, "volume": v} for t, o, h, l, c, v in zip(T, O, H, L, C, Vv)]
def agg(h, sec):
    out = []
    for c in h:
        ps = c["time"] // sec * sec
        if not out or out[-1]["time"] != ps: out.append(dict(c, time=ps))
        else:
            b = out[-1]; b["high"] = max(b["high"], c["high"]); b["low"] = min(b["low"], c["low"]); b["close"] = c["close"]; b["volume"] += c["volume"]
    return out
DATA = {}
def series(sym):
    if sym not in DATA:
        h = bars(sym); DATA[sym] = (h, [c["time"] for c in h], agg(h, 14400), agg(h, 86400))
    return DATA[sym]
# (1) parity
B = series("BTCUSDT")
rng = np.random.default_rng(1); tot = miss = 0; worst = np.zeros(29)
for sym in ("SOLUSDT", "1000PEPEUSDT", "LINKUSDT"):
    h, hT, h4, d = series(sym)
    z = np.load(f"lv2/{sym}.npz")
    idx = np.flatnonzero((z["fam"] >= 33) & (z["t"] >= 1672531200))
    for i in rng.choice(idx, 40, replace=False):
        t = int(z["t"][i]); J = bisect.bisect_left(hT, t); bj = bisect.bisect_left(B[1], t)
        cs = V.smc_candidates(h[max(0, J - 1000):J], [c for c in h4 if c["time"] + 14400 <= t][-1000:], [c for c in d if c["time"] + 86400 <= t],
                              B[0][max(0, bj - 1000):bj], [c for c in B[3] if c["time"] + 86400 <= t], t)
        m = [c for c in cs if c["fam"] == V.SMC_FAMS[int(z["fam"][i])] and c["side"] == int(z["side"][i])]
        tot += 1
        if not m or abs(m[0]["lv"] / float(z["lv"][i]) - 1) > 1e-6: miss += 1; continue
        worst = np.maximum(worst, np.abs(np.array(m[0]["f"]) - z["F"][i].astype(float)))
bad = [(nm, round(float(w), 4)) for nm, w in zip(V.SMC_FNAMES, worst) if w > 0.01 and nm != "conf"]
print(f"(1) parity: {tot} events, {miss} without the level, features off: {bad or 'none'}, conf max diff {worst[22]:.0f}")
ok &= miss <= 2 and not bad
# (2) the model
m = V.smc_model()
ok &= bool(m) and m["feats"] == V.SMC_FNAMES and m["fams"] == V.SMC_FAMS
print("(2) model", bool(m), m and m["ver"], m and m["thr"])
# (3) arm / fire / settle at backtest trades' hours
BT = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))["smc"]
def binance_name(gs):
    b = gs.replace("_USDT", "")
    for cand in (b + "USDT", "1000" + b + "USDT"):
        try: LE.load_np(cand); return cand, (1000.0 if cand.startswith("1000") else 1.0)
        except Exception: pass
    return None, 1
picks = [t for t in BT if t["t"] >= 1767225600][:6]
V.RESEARCH_COINS_127 = tuple(sorted({t["s"] for t in picks}))
V._research_syms = lambda coins, n=300: list(coins)
NOW = {"t": 0}
def fake_closed(sym, tf, sec, n, now):
    src = "BTCUSDT" if sym == "BTC_USDT" else binance_name(sym)[0]
    scl = 1.0 if sym == "BTC_USDT" else binance_name(sym)[1]
    h, hT, h4, d = series(src)
    lst = {"1h": h, "4h": h4, "1d": d}[tf]
    out = [c for c in lst if c["time"] + sec <= now][-n:]
    return [dict(c, open=c["open"] / scl, high=c["high"] / scl, low=c["low"] / scl, close=c["close"] / scl) for c in out]
def fake_range(sym, tf, a, b):
    src, scl = binance_name(sym); h = series(src)[0]
    return [dict(c, open=c["open"] / scl, high=c["high"] / scl, low=c["low"] / scl, close=c["close"] / scl) for c in h if a <= c["time"] <= b]
V._zm_closed = fake_closed
V.get_candles_range = fake_range
V.binance_klines = lambda *a, **k: []
V.limit_touched_since = lambda *a, **k: False
V.send_telegram = lambda *a, **k: None
V.notify_trade_result = lambda *a, **k: None
V.smc_save = lambda: None
V.heartbeat = lambda *a, **k: None
V.AUTOTRADE_ENABLED_SMC = False
real_time = time.time
hits = 0
for t in picks:
    V._SMC.update({"trades": [], "armed": [], "armed_at": None})
    time.time = lambda: t["t"] + 25
    V.smc_arm()
    arm = [a for a in V._SMC["armed"] if a["symbol"] == t["s"] and a["fam"] == t["lvl"] and a["side"] == t["d"]]
    if not arm:
        print("   not armed:", t["s"], t["lvl"], t["d"], time.strftime("%Y-%m-%d %H:%M", time.gmtime(t["t"])), [(a["symbol"], a["fam"]) for a in V._SMC["armed"]][:5]); continue
    a = arm[0]
    ok_lv = abs(a["lv"] / t["e"] - 1) < 1e-6
    V.smc_settle(t["t"] + 3600 + 30)                 # the touch hour closed: the armed level touched -> the trade
    time.time = lambda: t["x"] + 7200
    V.smc_settle(t["x"] + 7200)                      # walked to the end
    tr = [x for x in V._SMC["trades"] if x["symbol"] == t["s"]]
    r = tr[0]["r"] if tr else None
    same = r is not None and abs(r - t["r"]) < 0.02
    hits += ok_lv and same
    print(f"   {t['s']:12s} {t['lvl']:10s} {t['d']:+d} lv ok {ok_lv} · R bot {r} vs backtest {t['r']} {'✓' if same else '✗'}")
time.time = real_time
print(f"(3) {hits}/{len(picks)} backtest trades re-made by the bot")
ok &= hits >= len(picks) - 1
# (4) the risk fields
html = V.INDEX_HTML if hasattr(V, "INDEX_HTML") else open("/home/user/vp-poc-screener/vp_poc_screener.py").read()
src = open("/home/user/vp-poc-screener/vp_poc_screener.py").read()
a = src.index("const setInputs = {"); b = src.index("};", a); c = src.index("const setValueInputs = {"); e = src.index("};", c)
num_in_cb = [k for k in ("risk_pct_emw", "risk_pct_rbx", "risk_pct_cas", "risk_pct_smc") if k in src[a:b]]
in_val = [k for k in ("risk_pct_emw", "risk_pct_rbx", "risk_pct_cas", "risk_pct_smc") if k in src[c:e]]
print("(4) risk fields in the checkbox map:", num_in_cb, "· in the number map:", in_val)
ok &= not num_in_cb and len(in_val) == 4
V.save_settings = lambda *a, **k: None
try:
    V.apply_settings({"risk_pct_smc": "0.3"}); a1 = V.MODULE_RISK_PCT.get("smc")
    V.apply_settings({"risk_pct_smc": False}); a2 = V.MODULE_RISK_PCT.get("smc")
except Exception as e:
    a1 = a2 = f"err {e}"
print("    risk 0.3 ->", a1, "· then a stray false ->", a2)
ok &= a1 == 0.3 and a2 == 0.3
print("ALL OK" if ok else "FAILED")
sys.exit(0 if ok else 1)
