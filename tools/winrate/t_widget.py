"""v0.99.762 — the widget's numbers (/api/widget): every closed trade of the bundle (⚡, P/R, SMC, EMA, HTF), real or virtual;
the risk = a real trade's own, else the module's current %; R = a real ⚡ fill's r_real, else r; n days since the earliest;
the growth = the product of (1 + risk x R); the year = the balance x growth ^ (365 / n); the curve ends at today's balance"""
import os, sys, time, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import V
now = time.time(); d0 = now - 20 * 86400
V.BINANCE_API_KEY, V.BINANCE_API_SECRET = "k", "s"
V.bnf_account = lambda: {"wallet": 150.0, "equity": 160.0, "free": 100.0, "upnl": 10.0}
V.MODULE_RISK_PCT.update({"dlm": 4.0, "prv": 3.0, "smc": 2.5, "emw": 3.0, "htf": 2.0})
DV = V.DLM_MODEL_VER
STORES = {"dlm": (V._DLM, V._dlm_lock), "prv": (V._PRX, V._prx_lock), "smc": (V._SMC, V._smc_lock), "emw": (V._EMX, V._emx_lock), "htf": (V._HTF, V._htf_lock)}
T = {"dlm": [{"status": "CLOSED", "rv": DV, "t_in": d0, "t_out": d0 + 3600, "r": 1.2, "real": {"ex": "binance", "risk": 5.0, "r_real": 1.1}},
             {"status": "CLOSED", "rv": DV, "t_in": d0 + 86400, "t_out": d0 + 90000, "r": -1.0, "real": None},    # virtual: the module's 4%
             {"status": "CLOSED", "rv": 1, "t_in": d0, "t_out": d0 + 5, "r": 3.0, "real": None},                 # the old 15m module: not counted
             {"status": "OPEN", "rv": DV, "t_in": d0 + 3 * 86400, "r": None, "real": None}],
     "prv": [{"status": "CLOSED", "hour": d0 + 2 * 86400, "t_out": d0 + 2 * 86400 + 7200, "r": 0.8, "real": False}],
     "smc": [{"status": "CLOSED", "t_in": d0 + 4 * 86400, "t_out": d0 + 5 * 86400, "r": -0.5, "real": True},
             {"status": "CLOSED", "t_in": d0 + 4 * 86400, "t_out": d0 + 5 * 86400, "r": None, "result": "NO_FILL"}],
     "emw": [{"status": "CLOSED", "t_in": d0 + 6 * 86400, "t_out": d0 + 7 * 86400, "r": 2.0, "sel": True},
             {"status": "CLOSED", "t_in": d0 + 6 * 86400, "t_out": d0 + 7 * 86400, "r": 5.0, "sel": False}],   # not a selected coin
     "htf": [{"status": "CLOSED", "t_in": d0 + 8 * 86400, "t_out": d0 + 9 * 86400, "r": 1.5}]}
for k, (st, lk) in STORES.items():
    with lk: st["trades"] = list(T[k])
V._WIDGET["d"] = None
d = V.widget_data()
g = (1 + 0.05 * 1.1) * (1 - 0.04) * (1 + 0.03 * 0.8) * (1 - 0.025 * 0.5) * (1 + 0.03 * 2.0) * (1 + 0.02 * 1.5)
assert d["n"] == 6 and abs(d["days"] - 20) < 0.1, d
assert abs(d["growth_n"] - g) < 1e-4 and abs(d["year"] - 160 * g ** (365 / 20)) < 0.5, (d["growth_n"], g)
assert [m["n"] for m in d["mods"]] == [2, 1, 1, 1, 1], d["mods"]
assert d["curve"][0][0] == 0 and abs(d["curve"][-1][1] - 160) < 0.01 and abs(d["curve"][0][1] - 160 / g) < 0.01, d["curve"]
print(d["bal_s"], d["year_k"], d["mult_s"], d["profit_k"], "|", d["line"], "|", d["mods_s"], "|", d["warn"])
c = V.app.test_client().get("/api/widget", environ_base={"REMOTE_ADDR": "192.168.100.5"}).get_json()
assert c["bal_s"] == "$160" and c["year_s"] == d["year_s"], c
for k, (st, lk) in STORES.items():
    with lk: st["trades"] = []
V._WIDGET["d"] = None; e = V.widget_data(); assert e["year_s"] == "—" and e["curve"] == [] and "нет закрытых" in e["line"], e
print("t_widget OK")
