"""v0.99.733 — a backtest file fetched before a module's list was published (the 📏 HTF tab: "сделок нет") is refetched
when that module's list is asked for, at most once in 10 min; the repo's file has the HTF list"""
import sys, os, json, time, tempfile
from common import V
ok = True
repo = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))
ok &= len(repo.get("htf") or []) >= 250   # v0.99.738: 290 with the 1d close-stop
print("repo file: htf", len(repo.get("htf") or []))
bt = V.bt_trades = V._bt_trades_real              # the bot's own function (common.py swaps it for a read-only one)
fn = os.path.join(tempfile.mkdtemp(), "bt.json")
json.dump({"ver": 1, "smc": [{"t": 1, "r": 1.0}]}, open(fn, "w"))   # the stale copy: fresh by time, no "htf"
os.utime(fn, (time.time() + 60, time.time() + 60))
V.BT_TRADES_FILE = fn
calls = []
class R:
    def raise_for_status(self): pass
    def json(self): return {"ver": 1, "smc": [{"t": 1, "r": 1.0}], "htf": [{"t": 2, "r": 0.5, "x": 3}]}
V.requests.get = lambda *a, **k: calls.append(1) or R()
V._bt_cache.update({"d": None, "t": 0, "miss": 0})
d1 = bt(); n1 = len(calls)                         # fresh file -> no download
d2 = bt(need="smc"); n2 = len(calls)               # has smc -> no download
d3 = bt(need="htf"); n3 = len(calls)               # no htf -> the download
d4 = bt(need="htf"); n4 = len(calls)               # now cached
print("downloads", n1, n2, n3, n4, "· htf after", len(d3.get("htf") or []), "· saved", "htf" in json.load(open(fn)))
ok &= n1 == 0 and n2 == 0 and n3 == 1 and n4 == 1 and len(d3["htf"]) == 1 and "htf" in json.load(open(fn))
V._bt_cache.update({"d": {"ver": 1}, "t": time.time(), "miss": time.time()})
bt(need="htf"); ok &= len(calls) == 1                # missing again within 10 min -> no hammering
with V.app.test_client() as c:
    V._bt_cache.update({"d": None, "t": 0, "miss": 0})
    r = c.get("/api/bt/trades?mod=htf").get_json()
print("api htf trades", len(r["trades"]))
ok &= len(r["trades"]) == 1
print("ALL OK" if ok else "FAILED"); sys.exit(0 if ok else 1)
