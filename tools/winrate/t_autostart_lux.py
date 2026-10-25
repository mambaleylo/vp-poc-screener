"""v0.99.723 — "cd ~/storage/downloads/luxestetic && bash start.sh" in the autostart: whatever start.sh does (runs the bot
in the foreground / starts it in the background and exits / exec's it), the check starts it once, no second copy while it
runs, again after it stops; the folder through a symlink like Termux's ~/storage/downloads"""
import os, sys, time, subprocess, importlib.util, io, contextlib, signal
A = os.path.dirname(os.path.abspath(__file__)); H = os.path.join(A, "home"); os.environ["HOME"] = H; os.environ["VP_PORT"] = "18097"; sys.argv = ["x"]
spec = importlib.util.spec_from_file_location("vpbot", os.path.join(A, "bot", "vp_poc_screener.py")); V = importlib.util.module_from_spec(spec)
with contextlib.redirect_stdout(io.StringIO()): spec.loader.exec_module(V)
V._under_keepalive = lambda: True
LUX = os.path.join(H, "realdl", "luxestetic"); ST = os.path.join(H, "lux_starts.txt")
def kill_bot():
    for d in os.listdir("/proc"):
        if not d.isdigit(): continue
        try: a = open(f"/proc/{d}/cmdline", "rb").read().split(b"\0")
        except OSError: continue
        if a and b"python" in os.path.basename(a[0]) and any(x.endswith(b"notify_bot.py") for x in a[1:3]):
            os.kill(int(d), signal.SIGTERM)
starts = lambda: len(open(ST).read().split()) if os.path.exists(ST) else 0
V.autostart_set(True); p = V._autostart_paths(); open(p["keep"], "w").write("#!/bin/sh\nsleep 1\n")
ok_all = True
for nm, body in (("foreground", "python3 notify_bot.py\n"), ("background+exit", "nohup python3 notify_bot.py >/dev/null 2>&1 &\n"), ("exec", "exec python3 notify_bot.py\n")):
    kill_bot(); time.sleep(1)
    if os.path.exists(ST): os.remove(ST)
    open(os.path.join(LUX, "start.sh"), "w").write("#!/bin/sh\n" + body)
    lst = V.autostart_extra_set("cd ~/storage/downloads/luxestetic && bash start.sh"); time.sleep(4)
    s1 = starts()
    for _ in range(2): subprocess.run(["sh", p["check"]], timeout=60)
    time.sleep(3); s2 = starts()
    kill_bot(); time.sleep(2); subprocess.run(["sh", p["check"]], timeout=60); time.sleep(4); s3 = starts()
    ok = lst[0]["dir"] == os.path.realpath(LUX) and s1 == 1 and s2 == 1 and s3 == 2
    ok_all &= ok
    print(f"{nm}: dir {lst[0]['dir'] == os.path.realpath(LUX)} · started {s1} · after 2 checks {s2} (no second copy) · stopped -> {s3} (again)  {ok}")
kill_bot(); V.autostart_set(False)
print("ALL OK" if ok_all else "FAILED")
