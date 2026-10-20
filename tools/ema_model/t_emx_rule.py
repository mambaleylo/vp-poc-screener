"""v0.99.644 — the EMA rule's filters (emx_pass) and the status fields the tab uses."""
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
m = {"thr": 0.35, "sides": [1], "max_d_ema200": 10.0, "tf_margin": {"4h": 0.1}}
check("a long 1d touch above the threshold passes", V.emx_pass(m, "1d", 1, 0.36, {"s_d_ema200": 3.0}))
check("below the threshold: no", not V.emx_pass(m, "1d", 1, 0.34, {"s_d_ema200": 3.0}))
check("a short: no (longs only)", not V.emx_pass(m, "1d", -1, 0.9, {"s_d_ema200": 3.0}))
check("10+ daily ATR above the daily EMA200: no", not V.emx_pass(m, "1w", 1, 0.9, {"s_d_ema200": 10.5}))
check("4h needs the threshold + 0.1", not V.emx_pass(m, "4h", 1, 0.40, {"s_d_ema200": 1.0}) and V.emx_pass(m, "4h", 1, 0.46, {"s_d_ema200": 1.0}))
old = {"thr": 0.35}
check("a model without the fields takes the bot's defaults", not V.emx_pass(old, "1d", -1, 0.9, {"s_d_ema200": 0.0}) and V.emx_pass(old, "1d", 1, 0.36, {"s_d_ema200": 0.0}))
V._EMX["model"] = {"ver": 4, "q": 0.97, "thr": 0.35, "rule": {"stop_datr": 0.75, "take_r": 3.0, "hold_h": 72}, "sides": [1], "max_d_ema200": 10.0, "tf_margin": {"4h": 0.1}}
V._EMX["trades"] = [{"symbol": "SOL_USDT", "side": 1, "tf": "1d", "n": 50, "entry": 140.0, "sl": 133.0, "tp": 161.0, "t_in": 1, "hour": 0, "status": "CLOSED",
                     "result": "WIN", "r": 2.9, "exit": 161.0, "t_out": 9, "real": False, "sel": True}]
st = V.emx_stats()
check("status: the model's filters for the tab", st["model"]["sides"] == [1] and st["model"]["max_d_ema200"] == 10.0)
check("status: the last trades carry the chart's fields", all(k in st["last"][0] for k in ("entry", "sl", "tp", "exit", "t_out", "hour")))
print(f"{ok}/{ok + bad}")
