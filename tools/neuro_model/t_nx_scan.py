import time, json
exec(open("t_nx_e2e.py").read().split("MP = ")[0])
syms = ["SOLUSDT", "LINKUSDT", "DOGEUSDT", "AVAXUSDT", "XRPUSDT", "ADAUSDT", "ETHUSDT", "BNBUSDT", "LTCUSDT", "DOTUSDT"]
vp._own_top_syms = lambda n=None: [s.replace("USDT", "_USDT") for s in syms]
vp.get_tickers = lambda: []
vp.send_telegram = lambda *a, **k: print("TG", a[0][:80])
vp.nx_save = lambda: None
vp.AUTOTRADE_ENABLED_NEURO = False
vp._NX["model"] = json.load(open("vp_neuro_model.json"))
vp.nx_model()
now0 = 1745000000 // 3600 * 3600
vp.time.time = lambda: now0 + 60
t = time.perf_counter(); vp.nx_scan_once(); print("scan sec", round(time.perf_counter() - t, 1), vp._NX["scan"], vp._NX["last"][:3])
vp._NX["model"]["thr"] = {"1": 0.05, "-1": 0.05}
vp.nx_scan_once(); print(vp._NX["scan"]); print([ (t["symbol"], t["side"], round(t["sl"],4), round(t["tp"],4)) for t in vp._NX["trades"]])
vp.time.time = lambda: now0 + 20 * 3600
vp.get_candles_range = lambda sym, tf, a, b: [c for c in h1_of(sym.replace("_", "")) if a <= c["time"] <= b]
vp.nx_settle(); print([(t["symbol"], t["result"], t["r"], t["entry"]) for t in vp._NX["trades"]])
st = vp.nx_stats(); print(st["n"], st["avg"], st["per_week"])
