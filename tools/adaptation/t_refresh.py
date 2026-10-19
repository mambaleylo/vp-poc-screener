"""model_refresh_once: a newer model of the same version is taken, an older / another version is not"""
import sys, io, contextlib, json, os, tempfile
sys.argv = ["x"]; sys.path.insert(0, "/home/user/vp-poc-screener")
with contextlib.redirect_stdout(io.StringIO()):
    import vp_poc_screener as V
d = tempfile.mkdtemp()
V.log_error = lambda *a, **k: None
REMOTE = {}
class R:
    def __init__(self, j): self.j = j
    def raise_for_status(self): pass
    def json(self): return self.j
V.requests.get = lambda url, **k: R(REMOTE[url])
files = {}
for nm, attr, ver in (("zm", "ZM", V.ZM_MODEL_VER), ("emx", "EMX", V.EMX_MODEL_VER), ("nx", "NX", V.NX_MODEL_VER), ("prx", "PRX", V.PRX_MODEL_VER)):
    fn = os.path.join(d, nm + ".json"); setattr(V, f"{attr}_MODEL_FILE", fn); files[nm] = fn
    json.dump({"ver": ver, "models": [1], "trained_to": 1000}, open(fn, "w"))
    getattr(V, f"_{attr}")["model"] = {"cached": True}
url = lambda attr: getattr(V, f"{attr}_MODEL_URL").format(ref="main")
REMOTE[url("ZM")] = {"ver": V.ZM_MODEL_VER, "models": [1], "trained_to": 2000}          # newer -> taken
REMOTE[url("EMX")] = {"ver": V.EMX_MODEL_VER, "models": [1], "trained_to": 500}         # older -> not
REMOTE[url("NX")] = {"ver": V.NX_MODEL_VER + 1, "models": [1], "trained_to": 9000}     # another version -> not
REMOTE[url("PRX")] = {"ver": V.PRX_MODEL_VER, "models": [], "trained_to": 9000}         # empty -> not
done = V.model_refresh_once()
ok = 0; bad = 0
def check(n, c):
    global ok, bad
    if c: ok += 1
    else: bad += 1; print("FAIL", n)
check("only the zones taken", done == ["🎯 Сильные зоны"])
check("zones file replaced", json.load(open(files["zm"]))["trained_to"] == 2000)
check("zones cache cleared", V._ZM["model"] is None)
check("ema kept", json.load(open(files["emx"]))["trained_to"] == 1000 and V._EMX["model"] == {"cached": True})
check("another version kept", json.load(open(files["nx"]))["trained_to"] == 1000)
check("empty model kept", json.load(open(files["prx"]))["trained_to"] == 1000)
check("second run: nothing new", V.model_refresh_once() == [])
os.remove(files["emx"]); REMOTE[url("EMX")]["trained_to"] = 600
check("missing local file -> taken", V.model_refresh_once() == ["📐 EMA"])
print("ok", ok, "fail", bad)
