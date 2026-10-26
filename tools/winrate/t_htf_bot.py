"""v0.99.732 — 📏 HTF levels in the bot: (1) the bot's pure-Python HTF levels / features (smc_candidates, want = 0..22)
== the research engine's (lv2 npz) on Binance bars closed before the touch hour; (2) the model file loads, its features /
families match the code; (3) at the hour of 2026 backtest trades the bot arms that level (candles mocked from Binance
history), the hour's candle 0.1% through it opens the trade, the settle walks it to the backtest list's R; (4) the risk
field is a number field; (5) the trigger: the price at the level -> nothing, 0.1% through -> the touch; (6) on Binance
with the others (BN_OTHERS_MODES, 2% since v0.99.737)."""
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
WANT = set(range(23))
# (1) parity
B = series("BTCUSDT")
rng = np.random.default_rng(1); tot = miss = 0; worst = np.zeros(29)
for sym in ("SOLUSDT", "1000PEPEUSDT", "LINKUSDT", "AAVEUSDT"):
    h, hT, h4, d = series(sym)
    z = np.load(f"lv2/{sym}.npz")
    idx = np.flatnonzero((z["fam"] <= 22) & (z["side"] > 0) & (z["t"] >= 1672531200))
    for i in rng.choice(idx, 40, replace=False):
        t = int(z["t"][i]); J = bisect.bisect_left(hT, t); bj = bisect.bisect_left(B[1], t)
        cs = V.smc_candidates(h[max(0, J - 1000):J], [c for c in h4 if c["time"] + 14400 <= t][-1000:], [c for c in d if c["time"] + 86400 <= t],
                              B[0][max(0, bj - 1000):bj], [c for c in B[3] if c["time"] + 86400 <= t], t, want=WANT)
        m = [c for c in cs if c["fam"] == V.SMC_FAMS[int(z["fam"][i])] and c["side"] == 1]
        tot += 1
        if not m or abs(m[0]["lv"] / float(z["lv"][i]) - 1) > 1e-6: miss += 1; continue
        worst = np.maximum(worst, np.abs(np.array(m[0]["f"]) - z["F"][i].astype(float)))
bad = [(nm, round(float(w), 4)) for nm, w in zip(V.SMC_FNAMES, worst) if w > 0.01 and nm not in ("conf", "travel")]
print(f"(1) parity: {tot} events, {miss} without the level, features off: {bad or 'none'}, travel max diff {worst[7]:.3f}, conf {worst[22]:.0f}")
ok &= miss <= 2 and not bad and worst[7] < 0.05
# the SMC families are what they were (want=None)
h, hT, h4, d = series("SOLUSDT"); t = 1767225600 + 5 * 86400 + 7 * 3600; J = bisect.bisect_left(hT, t); bj = bisect.bisect_left(B[1], t)
args = (h[max(0, J - 1000):J], [c for c in h4 if c["time"] + 14400 <= t][-1000:], [c for c in d if c["time"] + 86400 <= t], B[0][max(0, bj - 1000):bj], [c for c in B[3] if c["time"] + 86400 <= t], t)
smc_only = V.smc_candidates(*args)
ok &= all(V.SMC_FAMS.index(c["fam"]) >= V.SMC_FIRST for c in smc_only)
print("    SMC's own call: only its families", all(V.SMC_FAMS.index(c["fam"]) >= V.SMC_FIRST for c in smc_only), len(smc_only))
# (2) the model
m = V.htf_model()
ok = bool(ok) and bool(m) and m["feats"] == V.SMC_FNAMES and m["fams"] == V.SMC_FAMS and bool(m["models_o"]) and bool(m["models_n"])
print("(2) model", bool(m), m and m["ver"], m and (round(m["thr_o"], 4), round(m["thr_n"], 4)))
# (3) arm / fire / settle at backtest trades' hours
BT = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))["htf"]
def binance_name(gs):
    b = gs.replace("_USDT", "")
    for cand in (b + "USDT", "1000" + b + "USDT"):
        try: LE.load_np(cand); return cand, (1000.0 if cand.startswith("1000") else 1.0)
        except Exception: pass
    return None, 1
picks = [t for t in BT if t["t"] >= 1767225600][::20][:7]
V.RESEARCH_COINS_127 = tuple(sorted({t["s"] for t in picks}))
V._research_syms = lambda coins, n=300, mode=None: list(coins)
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
V.mod_candles = lambda mode, sym, tf, a, b: fake_range(sym, tf, a, b)
V.limit_touched_since = lambda *a, **k: False
V.send_telegram = lambda *a, **k: None
V.notify_trade_result = lambda *a, **k: None
V.htf_save = lambda: None
V.heartbeat = lambda *a, **k: None
V.AUTOTRADE_ENABLED_HTF = False
real_time = time.time
hits = 0
for t in picks:
    V._HTF.update({"trades": [], "armed": [], "armed_at": None})
    time.time = lambda: t["t"] + 25
    V.htf_arm()
    arm = [a for a in V._HTF["armed"] if a["symbol"] == t["s"] and a["fam"] == t["lvl"]]
    if not arm:
        print("   not armed:", t["s"], t["lvl"], time.strftime("%Y-%m-%d %H:%M", time.gmtime(t["t"])), [(a["symbol"], a["fam"]) for a in V._HTF["armed"]][:5]); continue
    a = arm[0]
    ok_lv = abs(a["lv"] / t["e"] - 1) < 1e-6 and a["by"] == t["by"]
    V.htf_settle(t["t"] + 3600 + 30)                 # the touch hour closed: 0.1% through the armed level -> the trade
    time.time = lambda: t["x"] + 7200
    V.htf_settle(t["x"] + 7200)                      # walked to the end
    tr = [x for x in V._HTF["trades"] if x["symbol"] == t["s"]]
    r = tr[0]["r"] if tr else None
    same = r is not None and abs(r - t["r"]) < 0.02
    hits += ok_lv and same
    print(f"   {t['s']:12s} {t['lvl']:9s} by {a['by']:2s} lv ok {ok_lv} · R bot {r} vs backtest {t['r']} {'✓' if same else '✗'}")
time.time = real_time
print(f"(3) {hits}/{len(picks)} backtest trades re-made by the bot")
ok &= hits >= len(picks) - 1
# (4) the risk field
src = open("/home/user/vp-poc-screener/vp_poc_screener.py").read()
a = src.index("const setInputs = {"); b = src.index("};", a); c = src.index("const setValueInputs = {"); e = src.index("};", c)
ok &= "risk_pct_htf" not in src[a:b] and "risk_pct_htf" in src[c:e] and "htf_enabled" in src[a:b] and "autotrade_htf" in src[a:b]
V.save_settings = lambda *a, **k: None
try:
    V.apply_settings({"risk_pct_htf": "1.2", "autotrade_htf": True}); a1 = V.MODULE_RISK_PCT.get("htf"); a2 = V.AUTOTRADE_ENABLED_HTF
    V.apply_settings({"risk_pct_htf": "", "autotrade_htf": False}); a3 = V.MODULE_RISK_PCT.get("htf"); a4 = V.AUTOTRADE_ENABLED_HTF
except Exception as ex:
    a1 = a2 = a3 = a4 = f"err {ex}"
print("(4) risk 1.2 ->", a1, "autotrade", a2, "· cleared ->", a3, a4)
ok &= a1 == 1.2 and a2 is True and not a3 and a4 is False
# (5) the trigger: at the level nothing, 0.1% through the touch
V.binance_recent = lambda sym, since: None
lv = 100.0; trig = lv * 0.999
r1 = V.htf_touched("X_USDT", trig, 99.95, 0); r2 = V.htf_touched("X_USDT", trig, 99.9, 0)
V.binance_recent = lambda sym, since: (99.85, 100.2)
r3 = V.htf_touched("X_USDT", trig, 100.1, 0)
print("(5) price 99.95 ->", r1, "· 99.90 ->", r2, "· Binance 1-min low 99.85 ->", r3)
ok &= r1 is None and r2 == "px" and r3 == "binance"
# (6) Binance
print("(6) on Binance with the others:", "htf" in V.BN_OTHERS_MODES, V.BN_OTHERS_RISK.get("htf"))
ok &= "htf" in V.BN_OTHERS_MODES and V.BN_OTHERS_RISK.get("htf") == 2.0
print("ALL OK" if ok else "FAILED")
sys.exit(0 if ok else 1)
