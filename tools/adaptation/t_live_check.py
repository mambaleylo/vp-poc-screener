"""v0.99.648 — the live-vs-backtest check: statuses, the rule-version filter in the modules' stats."""
import sys, io, contextlib, os
sys.argv = ["x"]
sys.path.insert(0, os.environ.get("BOT", "/home/user/vp-poc-screener"))
with contextlib.redirect_stdout(io.StringIO()):
    import vp_poc_screener as V
ok = bad = 0
def check(name, cond):
    global ok, bad
    ok += bool(cond); bad += (not cond)
    print(("OK  " if cond else "FAIL") + " " + name)
V.bt_trades = lambda: {"prv": [{"r": x} for x in [1.0, -1.0, 0.5, 0.75] * 25]}     # mu 0.3125
lc = V.live_vs_bt("prv", [])
check("no live trades: the backtest's mean only", lc["n"] == 0 and abs(lc["mu"] - 0.312) < 0.01)
check("under 20 trades: early", V.live_vs_bt("prv", [0.5] * 10)["status"] == "early")
check("20 trades near the mean: ok", V.live_vs_bt("prv", [1.0, -1.0, 0.5, 0.75] * 5)["status"] == "ok")
check("20 trades far below: below", V.live_vs_bt("prv", [-1.0] * 14 + [0.75] * 6)["status"] == "below")
check("a module without a list: None", V.live_vs_bt("emx", [0.1]) is None)
V._PRX["trades"] = [{"status": "CLOSED", "r": -1.0, "hour": k, "rv": V.PRX_MODEL_VER - 1} for k in range(30)] + \
                   [{"status": "CLOSED", "r": 0.5, "hour": 100 + k, "rv": V.PRX_MODEL_VER} for k in range(5)]
st = V.prx_stats()
check("P/R stats: only the current rule's trades are judged", st["live_check"]["n"] == 5 and st["live_check"]["avg"] == 0.5)
print(f"{ok}/{ok + bad}")
