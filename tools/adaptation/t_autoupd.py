import sys, io, contextlib
sys.argv = ["x"]; sys.path.insert(0, "/home/user/vp-poc-screener")
with contextlib.redirect_stdout(io.StringIO()):
    import vp_poc_screener as V
V.log_error = lambda *a, **k: None
MSG, RESTART, DL = [], [], []
V.tg_outbox_push = MSG.append
V.self_restart = lambda why, d=1.5: RESTART.append(why)
V.zones_save = lambda: None
REMOTE = {"sha": "a" * 40, "ver": V.APP_VERSION, "code": 200}
class R:
    def __init__(self): self.status_code = REMOTE["code"]; self.text = REMOTE["sha"]
V.requests.get = lambda url, **k: R()
def dl(only_if_newer=False):
    DL.append(1); return REMOTE["ver"]
V.self_update_download = dl
ok = bad = 0
def check(n, c):
    global ok, bad
    if c: ok += 1
    else: bad += 1; print("FAIL", n)
check("a new commit, the same version: no restart", V.auto_update_check() is None and not RESTART and len(DL) == 1)
check("the same commit again: nothing downloaded", V.auto_update_check() is None and len(DL) == 1)
REMOTE.update(sha="b" * 40, ver="9.9.9")
check("a new commit with a new version: restart", V.auto_update_check() == "9.9.9" and RESTART == ["update"] and "9.9.9" in MSG[-1])
REMOTE.update(code=403)
try:
    V.auto_update_check(); check("api refused -> error", False)
except RuntimeError:
    check("api refused -> error", True)
check("setting in the settings", "auto_update" in V.get_settings())
V.apply_settings({"auto_update": False}); check("switch off", V.AUTO_UPDATE is False)
print("ok", ok, "fail", bad)
