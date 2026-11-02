"""v0.99.761 — the widget's numbers (/api/widget): the balance, n days since the first real ⚡ trade, the growth = the product
of (1 + risk x R) over the closed real trades (r_real first), the year = the balance x growth ^ (365 / n)"""
import os, sys, time, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import V
now = time.time(); d0 = now - 20 * 86400
V.BINANCE_API_KEY, V.BINANCE_API_SECRET = "k", "s"
V.bnf_account = lambda: {"wallet": 150.0, "equity": 160.0, "free": 100.0, "upnl": 10.0}
T = [{"status": "CLOSED", "t_in": d0, "t_out": d0 + 3600, "r": 1.2, "real": {"ex": "binance", "risk": 4.0, "r_real": 1.1}},
     {"status": "CLOSED", "t_in": d0 + 86400, "t_out": d0 + 90000, "r": -1.0, "real": {"ex": "binance", "risk": 2.0}},
     {"status": "CLOSED", "t_in": d0 + 2 * 86400, "t_out": d0 + 2 * 86400 + 5, "r": 0.5, "real": None},   # virtual: not counted
     {"status": "OPEN", "t_in": d0 + 3 * 86400, "r": None, "real": {"ex": "binance", "risk": 4.0}}]
with V._dlm_lock:
    V._DLM["trades"].clear(); V._DLM["trades"].extend(T)
d = V.widget_data()
g = (1 + 0.04 * 1.1) * (1 - 0.02)
assert d["n"] == 2 and d["open"] == 1 and abs(d["days"] - 20) < 0.1, d
assert abs(d["growth_n"] - g) < 1e-4 and abs(d["year"] - 160 * g ** (365 / 20)) < 0.5, (d, 160 * g ** (365 / 20))
print(d["bal_s"], d["year_s"], d["mult_s"], d["profit_s"], d["pct_s"], "|", d["line"], "|", d["warn"])
c = V.app.test_client().get("/api/widget", environ_base={"REMOTE_ADDR": "127.0.0.1"}).get_json()
assert c["bal_s"] == "$160" and c["year_s"] == d["year_s"], c
with V._dlm_lock: V._DLM["trades"].clear()
V._WIDGET["d"] = None; e = V.widget_data(); assert e["year_s"] == "—" and "нет закрытых" in e["line"], e
print("t_widget OK")
