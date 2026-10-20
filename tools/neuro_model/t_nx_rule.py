"""v0.99.650 — the Neuro rule's filters (nx_pass) and the model file."""
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
def row(adx, b1):
    r = [0.0] * len(V.NX_NAMES); r[V.NX_NAMES.index("adx")] = adx; r[V.NX_NAMES.index("b_r1")] = b1; return r
m = {"max_adx": 30.0, "btc_1h": 1.0}
check("ADX 25, BTC flat: in", V.nx_pass(m, 1, row(25, 0.0)))
check("ADX 31: out", not V.nx_pass(m, 1, row(31, 0.0)))
check("a long after BTC -1.2% in the last hour: out", not V.nx_pass(m, 1, row(20, -1.2)))
check("a short after BTC -1.2%: in", V.nx_pass(m, -1, row(20, -1.2)))
check("a short after BTC +1.5%: out", not V.nx_pass(m, -1, row(20, 1.5)))
V.NX_MODEL_FILE = os.path.join(os.path.dirname(V.__file__), "vp_neuro_model.json")
mo = V.nx_model()
check("the model file ver 3 loads with the 24 h hold", mo and mo["ver"] == 3 and mo["rule"]["hold_h"] == 24 and mo.get("max_adx") == 30.0)
print(f"{ok}/{ok + bad}")
