import os, sys, importlib.util, io, contextlib
A = os.path.dirname(os.path.abspath(__file__)); os.environ["HOME"] = os.path.join(A, "home"); sys.argv = ["x"]
spec = importlib.util.spec_from_file_location("vpbot", os.path.join(A, "bot", "vp_poc_screener.py")); V = importlib.util.module_from_spec(spec)
with contextlib.redirect_stdout(io.StringIO()): spec.loader.exec_module(V)
V._under_keepalive = lambda: True
st0 = V.autostart_set(True)                                   # no Termux:API yet
os.environ["PATH"] = os.path.join(A, "fakebin") + ":" + os.environ["PATH"]   # Termux:API installed later
st1 = V.autostart_status()                                   # the window opened again: registered by itself
st2 = V.autostart_status()                                   # no second registration
n = len(open(os.path.join(A, "fakebin", "jobs.txt")).read().split())
st3 = V.autostart_set(False)
ok = st0["job"] is False and st0["job_set"] is False and st1["job"] and st1["job_set"] and st2["job_set"] and n == 1 and not st3["job_set"]
print(st0["job"], st0["job_set"], "->", st1["job"], st1["job_set"], "registrations", n, "off ->", st3["job_set"]); print("ALL OK" if ok else "FAILED")
