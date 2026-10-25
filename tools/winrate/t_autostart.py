"""v0.99.721 — the autostart scripts: written next to the bot and to ~/.termux/boot, valid sh; the keepalive loop restarts
a crashing bot and stops on the "off" file; the check starts the loop only when the bot does not answer"""
import os, sys, time, subprocess, importlib.util
A = os.path.dirname(os.path.abspath(__file__)); os.environ["HOME"] = os.path.join(A, "home"); os.environ["VP_PORT"] = "18099"
sys.argv = ["x"]
spec = importlib.util.spec_from_file_location("vpbot", os.path.join(A, "bot", "vp_poc_screener.py")); V = importlib.util.module_from_spec(spec)
import io, contextlib
with contextlib.redirect_stdout(io.StringIO()): spec.loader.exec_module(V)
V._under_keepalive = lambda: True   # no hand-over in the test
res = {}
st = V.autostart_set(True); p = V._autostart_paths()
res["files"] = all(os.path.exists(p[k]) for k in ("keep", "check", "boot")) and st["on"] and st["boot"] and p["boot"].startswith(os.environ["HOME"])
res["sh -n"] = all(subprocess.run(["sh", "-n", p[k]]).returncode == 0 for k in ("keep", "check", "boot"))
# a fake bot: logs a start, exits at once -> the loop must start it again after 10 s
fake = os.path.join(A, "bot", "fake_bot.py"); open(fake, "w").write("import time\nopen('starts.txt', 'a').write(str(time.time()) + '\\n')\n")
sc = V._autostart_scripts(dict(p, bot=fake)); open(p["keep"], "w").write(sc["keep"]); open(p["check"], "w").write(sc["check"])
for f_ in ("starts.txt",):
    try: os.remove(os.path.join(A, "bot", f_))
    except OSError: pass
subprocess.run(["sh", p["check"]], timeout=30)   # nothing answers on 18099 -> the loop starts
time.sleep(24)
n = len(open(os.path.join(A, "bot", "starts.txt")).read().split()) if os.path.exists(os.path.join(A, "bot", "starts.txt")) else 0
res["check starts the loop, the loop restarts a crashed bot"] = n >= 3   # at 0, 10, 20 s
pid = int(open(p["pid"]).read()); subprocess.run(["sh", p["check"]], timeout=30); time.sleep(1)
res["a second check: no second loop"] = int(open(p["pid"]).read()) == pid
st2 = V.autostart_set(False); time.sleep(12)
alive = os.path.exists(f"/proc/{pid}")
res["off: the loop ends, the boot script gone"] = not alive and not st2["on"] and not os.path.exists(p["boot"])
# the check when the bot answers: does nothing
import threading, http.server
srv = http.server.HTTPServer(("127.0.0.1", 18099), http.server.SimpleHTTPRequestHandler); threading.Thread(target=srv.serve_forever, daemon=True).start()
os.remove(p["off"]); os.remove(p["pid"]); before = len(open(os.path.join(A, "bot", "starts.txt")).read().split())
open(p["check"], "w").write(sc["check"].replace("/api/health", "/"))
subprocess.run(["sh", p["check"]], timeout=30); time.sleep(3)
res["the bot answers -> the check starts nothing"] = not os.path.exists(p["pid"]) and len(open(os.path.join(A, "bot", "starts.txt")).read().split()) == before
srv.shutdown(); open(p["off"], "w").write("off")
print(" · ".join(f"{k} {v}" for k, v in res.items()), f"(starts {n})")
print("ALL OK" if all(res.values()) else "FAILED")
