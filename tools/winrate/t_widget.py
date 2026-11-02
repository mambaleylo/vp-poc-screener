"""v0.99.762 — the widget's numbers (/api/widget): every closed trade of the bundle (⚡, P/R, SMC, EMA, HTF), real or virtual;
the risk = a real trade's own, else the module's current %; R = a real ⚡ fill's r_real, else r; n days since the earliest;
the growth = the product of (1 + risk x R); the year = the balance x growth ^ (365 / n); the curve ends at today's balance"""
import os, sys, time, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import V
now = time.time(); d0 = now - 20 * 86400
V.BINANCE_API_KEY, V.BINANCE_API_SECRET = "k", "s"
V.bnf_account = lambda: {"wallet": 150.0, "equity": 160.0, "free": 100.0, "upnl": 10.0}
V.bnf_req = lambda *a, **k: []   # no real Binance call (the income history: below)
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
# v0.99.763 — the income history: transfers = put in, the rest = the real PnL; the real curve starts at 0 (a new account), the
# transfers marked, the last point = today's equity
import tempfile
V.BN_INCOME_FILE = os.path.join(tempfile.mkdtemp(), "inc.json")
ms = lambda dd: int((d0 + dd * 86400) * 1000)
INC = [{"tranId": 1, "incomeType": "TRANSFER", "income": "100", "asset": "USDT", "time": ms(0.5)},
       {"tranId": 2, "incomeType": "REALIZED_PNL", "income": "12.5", "asset": "USDT", "symbol": "BTCUSDT", "time": ms(2)},
       {"tranId": 3, "incomeType": "COMMISSION", "income": "-0.5", "asset": "USDT", "symbol": "BTCUSDT", "time": ms(2)},
       {"tranId": 4, "incomeType": "TRANSFER", "income": "50", "asset": "USDT", "time": ms(10)},
       {"tranId": 5, "incomeType": "FUNDING_FEE", "income": "-2", "asset": "USDT", "symbol": "ETHUSDT", "time": ms(12)},
       {"tranId": 6, "incomeType": "COMMISSION", "income": "-0.01", "asset": "BNB", "symbol": "ETHUSDT", "time": ms(12)}]
calls = []
def fake_req(m, path, params=None, **kw):
    if path == "/fapi/v1/premiumIndex":
        return {"markPrice": "600"} if params["symbol"] == "BNBUSDT" else {}
    assert path == "/fapi/v1/income"; calls.append(params)
    return [x for x in INC if params["startTime"] <= x["time"] <= params["endTime"]]
V.bnf_req = fake_req
V.bnf_account = lambda: {"wallet": 160.0, "equity": 170.0, "free": 100.0, "upnl": 10.0}
V._INC.update({"rows": None, "t_fetch": 0.0}); V._WIDGET["d"] = None
d = V.widget_data(); sm = d["real"]
assert sm["dep"] == 150 and sm["pnl"] == 4 and sm["upnl"] == 10 and sm["real"] == 14, sm   # the BNB commission -0.01 x $600
assert abs(sm["rcurve"][0][1] - 6) < 0.01 and sm["rcurve"][-1][1] == 170 and [x[1] for x in sm["rdeps"]] == [100, 50], sm
print(d["real_line"]); n_calls = len(calls)
V._WIDGET["d"] = None; V.widget_data(); assert len(calls) == n_calls   # within 5 min: no new requests
V._INC.update({"rows": None, "t_fetch": 0.0}); V._WIDGET["d"] = None; V.widget_data()   # from the file: only from its last row on
assert calls[n_calls]["startTime"] == ms(12) + 1 and len(V._INC["rows"]) == 6, calls[n_calls]
c = V.app.test_client().get("/api/widget", environ_base={"REMOTE_ADDR": "192.168.100.5"}).get_json()
assert c["bal_s"] == "$170" and c["real_line"] == d["real_line"], c
for k, (st, lk) in STORES.items():
    with lk: st["trades"] = []
V._WIDGET["d"] = None; e = V.widget_data(); assert e["year_s"] == "—" and e["curve"] == [] and "нет закрытых" in e["line"], e
print("t_widget OK")
