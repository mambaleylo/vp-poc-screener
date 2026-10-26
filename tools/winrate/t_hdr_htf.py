"""v0.99.735 — the header's yearly expectation: ⚡ alone / the bundle / the bundle + 📏 HTF when HTF's real trades are on"""
import sys
from common import V
out = {}
with V.app.test_client() as c:
    for bn, htf in ((False, False), (False, True), (True, False), (True, True)):
        V.BN_OTHERS, V.AUTOTRADE_ENABLED_HTF = bn, htf
        e = c.get("/api/boot").get_json()["expect"]; out[(bn, htf)] = (e["kind"], e["p50"])
print(out)
ok = (out[(False, False)][0] == out[(False, True)][0] == "dlm" and out[(True, False)] == ("bundle", 40219) and out[(True, True)] == ("bundle_htf", 41745))
src = open("/home/user/vp-poc-screener/vp_poc_screener.py").read()
ok &= "e.kind === 'bundle_htf' ? '⚡ + P/R + SMC + EMA + HTF'" in src
print("ALL OK" if ok else "FAILED"); sys.exit(0 if ok else 1)
