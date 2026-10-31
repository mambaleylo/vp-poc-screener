"""v0.99.743 — the model refresh takes any change of the repo's file (⚡'s exits of v0.99.692–694 came in the same file
with the same "trained_to", the phone kept the old rule): (1) the same version and date, other rules -> taken, the module
reloads it; (2) the same file -> not rewritten; (3) an older date in the repo -> kept; (4) another version -> kept"""
import os, sys, json, copy
from common import V
ok = True
repo = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "vp_dlm_model.json")))
old = copy.deepcopy(repo)
for st in old["streams"]:   # the phone's file: the rule before v0.99.692
    st.update({"take_atr": 1.0, "stop_mode": None, "hard_stop_atr": None, "close_h": None})
REM = {"m": repo}
class R:
    def __init__(s, j): s._j = j
    def raise_for_status(s): pass
    def json(s): return copy.deepcopy(s._j)
V.requests.get = lambda url, params=None, timeout=None, **k: R(REM["m"] if "vp_dlm_model" in url else {"ver": -1})
V.log_error = lambda m: None
def put(m):
    with open(V.DLM_MODEL_FILE, "w") as f: json.dump(m, f)
    V._DLM["model"] = None
put(old); V.dlm_model()
before = V._dlm_stream("close2h")
done = V.model_refresh_once()
V.dlm_model(); after = V._dlm_stream("close2h")   # the module reloads it on its next use
r1 = "⚡ Лимитки 4ч+2ч" in done and before.get("stop_mode") is None and after.get("stop_mode") == "close1h" and after.get("take_atr") == 1.1
print("(1) the same date, other rules -> taken:", r1, done); ok &= r1
mt = os.path.getmtime(V.DLM_MODEL_FILE); os.utime(V.DLM_MODEL_FILE, (mt - 100, mt - 100)); mt = os.path.getmtime(V.DLM_MODEL_FILE)
done2 = V.model_refresh_once()
r2 = "⚡ Лимитки 4ч+2ч" not in done2 and os.path.getmtime(V.DLM_MODEL_FILE) == mt
print("(2) the same file -> not rewritten:", r2); ok &= r2
newer = copy.deepcopy(old); newer["trained_to"] = repo["trained_to"] + 86400; put(newer)
r3 = "⚡ Лимитки 4ч+2ч" not in V.model_refresh_once() and json.load(open(V.DLM_MODEL_FILE))["trained_to"] == newer["trained_to"]
print("(3) the repo's older -> kept:", r3); ok &= r3
put(old); REM["m"] = dict(repo, ver=repo["ver"] + 1)
r4 = "⚡ Лимитки 4ч+2ч" not in V.model_refresh_once() and json.load(open(V.DLM_MODEL_FILE)) == old
print("(4) another version -> kept:", r4); ok &= r4
print("ALL OK" if ok else "FAILED"); sys.exit(0 if ok else 1)
