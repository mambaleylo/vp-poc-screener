"""The bot's own code replayed hour by hour over a past period on Binance's 1h candles (the lab-store, extended by
tools/yearly/extend_data.py) — the user: "до сих пор ни одной почти сделки" (SMC, EMA, HTF, Классика: 0 live trades in three weeks):
is the market quiet, or does the live bot miss what its own rule gives on the candles? The bot == the research on history (the
parity tests), so the replay is the backtest of the period by the deployed model.
🧱 SMC and 📏 HTF: at each hour the settle (the armed level touched in the hour just closed -> the trade, the open ones walked),
then the arming of the new hour — the live loop's order. -> <out>.json: the trades, and per hour the best score against the
threshold. usage: python3 replay_live.py smc|htf 2026-10-19 2026-11-10 out.json [part k of n]"""
import sys, json, time, bisect, calendar
from common import V, load

MOD, D0, D1, OUT = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
K, N = (int(sys.argv[5]), int(sys.argv[6])) if len(sys.argv) > 6 else (0, 1)
ts = lambda s: calendar.timegm(time.strptime(s, "%Y-%m-%d"))
T0, T1 = ts(D0), ts(D1) + 86400


def agg(h, sec):
    out = []
    for c in h:
        ps = c["time"] // sec * sec
        if not out or out[-1]["time"] != ps:
            out.append(dict(c, time=ps))
        else:
            b = out[-1]; b["high"] = max(b["high"], c["high"]); b["low"] = min(b["low"], c["low"]); b["close"] = c["close"]; b["volume"] += c["volume"]
    return out


DATA, NAME = {}, {}


def bname(gs):
    if gs not in NAME:
        b = gs.replace("_USDT", ""); NAME[gs] = (None, 1.0)
        for cand in (b + "USDT", "1000" + b + "USDT"):
            h = load(cand)
            if h:
                scl = 1000.0 if cand.startswith("1000") and not b.startswith("1000") else 1.0
                h = [dict(c, open=c["open"] / scl, high=c["high"] / scl, low=c["low"] / scl, close=c["close"] / scl) for c in h if c["time"] >= T0 - 3100 * 86400]
                DATA[gs] = {"1h": h, "4h": agg(h, 14400), "1d": agg(h, 86400)}
                DATA[gs]["T"] = {k: [c["time"] for c in v] for k, v in DATA[gs].items()}
                NAME[gs] = (cand, scl); break
    return NAME[gs]


def fake_closed(sym, tf, sec, n, now):
    if not bname(sym)[0]:
        return []
    d = DATA[sym]; j = bisect.bisect_right(d["T"][tf], now - sec)   # the bars closed by now
    return d[tf][max(0, j - n):j]


def fake_range(sym, tf, a, b):
    if not bname(sym)[0]:
        return []
    tf = tf if tf in ("1h", "4h", "1d") else "1h"
    d = DATA[sym]; i = bisect.bisect_left(d["T"][tf], a); j = bisect.bisect_right(d["T"][tf], b)
    return d[tf][i:j]


FUND = {}


def fake_funding(sym, now):   # the research's: Binance's settled funding (the live bot asks Gate's)
    if sym not in FUND:
        FUND[sym] = []
        try:
            import os
            fn = os.path.join(os.environ.get("LABSTORE", "/home/user/vp-lab-store"), "data", "funding", f"{bname(sym)[0]}.csv")
            FUND[sym] = [(int(a), float(b)) for a, b in (ln.strip().split(",")[:2] for ln in open(fn) if ln.strip())]
        except Exception:
            pass
    f = FUND[sym]; j = bisect.bisect_right([x[0] for x in f[-400:]], now)
    return f[-400:][max(0, j - 100):j]


coins = sorted(V.RESEARCH_COINS_211 if MOD == "prv" else V.RESEARCH_COINS_127)[K::N]
V.RESEARCH_COINS_127 = V.RESEARCH_COINS_211 = tuple(coins)
V._nx_funding = fake_funding; V.mod_px_map = lambda *a, **k: {}; V.limit_touched = lambda *a, **k: None
V._research_syms = lambda c, n=300, mode=None: list(c)
V._zm_closed = fake_closed; V.get_candles_range = fake_range; V.mod_candles = lambda mode, sym, tf, a, b: fake_range(sym, tf, a, b)
V.binance_klines = lambda *a, **k: []; V.limit_touched_since = lambda *a, **k: False
V.send_telegram = lambda *a, **k: None; V.notify_trade_result = lambda *a, **k: None; V.heartbeat = lambda *a, **k: None
V.tg_outbox_push = lambda *a, **k: None; V.execute_autotrade = lambda *a, **k: {"status": "SKIPPED", "detail": "replay"}
errs = []; V.log_error = lambda m: errs.append(str(m)[:200])
if MOD == "smc":
    V.smc_save = lambda: None; V.AUTOTRADE_ENABLED_SMC = False; ST, arm, settle, model = V._SMC, V.smc_arm, V.smc_settle, V.smc_model()
    thr = {"": float(model["thr"])}
elif MOD == "htf":
    V.htf_save = lambda: None; V.AUTOTRADE_ENABLED_HTF = False; ST, arm, settle, model = V._HTF, V.htf_arm, V.htf_settle, V.htf_model()
    thr = {"o": float(model["thr_o"]), "n": float(model["thr_n"])}
elif MOD == "emw":
    V.emx_save = lambda: None; V.AUTOTRADE_ENABLED_EMW = False; ST, arm, settle, model = V._EMX, V.emx_arm, V.emx_settle, V.emx_model()
    thr = {"": model.get("thr")}
else:   # P/R: the hour's scan makes the pending limits, the settle fills / walks them on the closed candles
    import os
    if os.environ.get("PRV_MODEL"):   # the model that was live in the period (P/R is retrained monthly: today's has seen it)
        V.PRX_MODEL_FILE = os.environ["PRV_MODEL"]; V._PRX["model"] = None
    V.prx_save = lambda: None; V.AUTOTRADE_ENABLED_PRV = False; ST, arm, settle, model = V._PRX, V.prx_scan_once, V.prx_settle, V.prx_model()
    thr = {str(k): v for k, v in (model.get("thr") or {}).items()}
ST.update({"trades": [], "armed": [], "armed_at": None, "loaded": True, "scan": None, "last": []})
have = [c for c in coins if bname(c)[0]]
stale = [c for c in have if DATA[c]["T"]["1h"][-1] < T1 - 3 * 86400]   # no fresh candles in the store (delisted / not extended): out
have = [c for c in have if c not in stale]
V.RESEARCH_COINS_127 = V.RESEARCH_COINS_211 = tuple(have)
last = min(DATA[c]["T"]["1h"][-1] for c in have)
if stale: print("без свежих свечей:", stale, flush=True)
print(f"{MOD}: монет {len(have)} из {len(coins)}, свечи по {time.strftime('%Y-%m-%d %H:%M', time.gmtime(last))}, порог {thr}", flush=True)
real_time = time.time; t_run = real_time(); hours = []
h = T0
while h < min(T1, last + 3600):
    time.time = lambda: h + 25
    settle(h + 25)
    arm()
    sc = ST.get("scan") or {}
    near = (sc.get("near") or []) + (ST.get("last") or [])
    hours.append({"h": h, "armed": len(ST.get("armed") or []), "levels": sc.get("levels") or sc.get("events"), "sig": sc.get("signals"), "best": max([x.get("pct") or 0 for x in near] or [0]),
                  "open": sum(1 for t in ST["trades"] if t["status"] == "OPEN")})
    if (h - T0) % 86400 == 0:
        print(time.strftime("%m-%d", time.gmtime(h)), "сделок", len(ST["trades"]), "взведено", len(ST.get("armed") or []), "лучший % порога", hours[-1]["best"], f"{real_time() - t_run:.0f}s", flush=True)
    h += 3600
time.time = real_time
keep = ("symbol", "fam", "side", "direction", "entry", "sl", "tp", "t_in", "hour", "status", "result", "r", "t_out", "score", "by", "so", "sn", "tf", "lv", "rt", "ema", "kind")
json.dump({"mod": MOD, "from": D0, "to": D1, "coins": len(have), "last": last, "thr": thr, "trades": [{k: t.get(k) for k in keep} for t in ST["trades"]],
           "hours": hours, "errs": errs[:20], "n_errs": len(errs)}, open(OUT, "w"))
print(f"replay done: {MOD} сделок {len(ST['trades'])}, ошибок {len(errs)}, {real_time() - t_run:.0f}s", flush=True)
