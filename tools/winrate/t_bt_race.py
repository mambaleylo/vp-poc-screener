"""v0.99.788 — the backtest list downloaded by many at once (the bot's start: the modules, the watchdog, the report): one
download, no "No such file or directory: vp_bt_trades.json.new -> vp_bt_trades.json" (two writers shared one temp name),
every caller gets the list, the file whole"""
import time, json, os, tempfile, threading
from common import V
ok = True
def chk(nm, c):
    global ok
    print(("OK  " if c else "FAIL") + " " + nm); ok &= bool(c)
d = tempfile.mkdtemp(prefix="vpbt_"); V.BT_TRADES_FILE = os.path.join(d, "vp_bt_trades.json")
DATA = {"ver": 1, "made": 1, "cfl": [{"t": 1, "r": 1.0}]}
n = {"get": 0}
class R:
    def raise_for_status(self): pass
    def json(self): time.sleep(0.3); return json.loads(json.dumps(DATA))
def get(url, params=None, timeout=None):
    n["get"] += 1; return R()
V.requests.get = get
logs = []; V.log_error = lambda m: logs.append(m)
V._bt_cache.update({"d": None, "t": 0})
out = [None] * 8
def call(i): out[i] = V._bt_trades_real()
th = [threading.Thread(target=call, args=(i,)) for i in range(8)]
[t.start() for t in th]; [t.join() for t in th]
chk(f"8 одновременных запросов — одно скачивание ({n['get']})", n["get"] == 1)
chk(f"ошибок нет ({logs[:1]})", not logs)
chk("у всех — список", all(o and o.get("cfl") for o in out))
chk("файл целый, временных не осталось", json.load(open(V.BT_TRADES_FILE))["cfl"][0]["r"] == 1.0 and not [f for f in os.listdir(d) if f.endswith(".new")])
print("t_bt_race OK" if ok else "t_bt_race FAIL")
