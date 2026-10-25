"""v0.99.723 — another program in the autostart: the check starts it unless running (no second copy), the bashrc line
added once and removed with the autostart off"""
import os, sys, time, subprocess, importlib.util, io, contextlib
A = os.path.dirname(os.path.abspath(__file__)); H = os.path.join(A, "home"); os.environ["HOME"] = H; os.environ["VP_PORT"] = "18098"; sys.argv = ["x"]
spec = importlib.util.spec_from_file_location("vpbot", os.path.join(A, "bot", "vp_poc_screener.py")); V = importlib.util.module_from_spec(spec)
with contextlib.redirect_stdout(io.StringIO()): spec.loader.exec_module(V)
V._under_keepalive = lambda: True
open(os.path.join(H, ".bashrc"), "w").write("alias ll='ls -l'\n")
res = {}
import signal
def kill_py(word):   # only python processes running that file (not a shell whose text holds the word)
    for d in os.listdir("/proc"):
        if not d.isdigit() or int(d) == os.getpid(): continue
        try: a = open(f"/proc/{d}/cmdline", "rb").read().split(b"\0")
        except OSError: continue
        if a and b"python" in os.path.basename(a[0]) and any(x.endswith(word.encode()) for x in a[1:3]):
            try: os.kill(int(d), signal.SIGTERM)
            except OSError: pass
V.autostart_set(True); p = V._autostart_paths()
open(p["keep"], "w").write("#!/bin/sh\nsleep 300\n")   # no real bot in the test
lst = V.autostart_extra_set(f"cd {H}/lux && python3 luxbot.py"); time.sleep(4)
starts = lambda: len(open(os.path.join(H, "lux_starts.txt")).read().split()) if os.path.exists(os.path.join(H, "lux_starts.txt")) else 0
res["marker"] = lst[0]["marker"] == "luxbot.py"
res["started now"] = starts() == 1
res["sh -n"] = subprocess.run(["sh", "-n", p["check"]]).returncode == 0
subprocess.run(["sh", p["check"]], timeout=30); subprocess.run(["sh", p["check"]], timeout=30); time.sleep(2)
res["running -> no second copy"] = starts() == 1
br = open(os.path.join(H, ".bashrc")).read()
V.autostart_set(True)
res["bashrc: one line, the user's lines kept"] = br.count(V.BASHRC_MARK) == 1 and open(os.path.join(H, ".bashrc")).read().count(V.BASHRC_MARK) == 1 and "alias ll" in br
st = V.autostart_status(); res["status"] = st["bashrc"] and st["extras"][0]["cmd"].endswith("luxbot.py")
kill_py("luxbot.py"); time.sleep(1)
subprocess.run(["sh", p["check"]], timeout=30); time.sleep(3)
res["stopped -> started again by the check"] = starts() == 2
V.autostart_set(False)
res["off: the bashrc line gone, the user's kept"] = V.BASHRC_MARK not in open(os.path.join(H, ".bashrc")).read() and "alias ll" in open(os.path.join(H, ".bashrc")).read()
kill_py("luxbot.py")
print(" · ".join(f"{k} {v}" for k, v in res.items())); print("ALL OK" if all(res.values()) else "FAILED")
