"""v0.99.735 — the header's yearly expectation: ⚡ alone / the bundle / the bundle + 📏 HTF when HTF's real trades are on;
v0.99.776 — + 🔄 Классика when its real trades are on (bundle_cfl / bundle_htf_cfl) and the label says so"""
import sys
from common import V
out = {}
with V.app.test_client() as c:
    for bn, htf, cfl in ((False, False, False), (False, True, True), (True, False, False), (True, True, False), (True, False, True), (True, True, True)):
        V.BN_OTHERS, V.AUTOTRADE_ENABLED_HTF, V.AUTOTRADE_ENABLED_CFL = bn, htf, cfl
        e = c.get("/api/boot").get_json()["expect"]; out[(bn, htf, cfl)] = (e["kind"], e["p50"])
print(out)
E = V.EXPECT_YEAR
ok = (out[(False, False, False)][0] == out[(False, True, True)][0] == "dlm" and out[(True, False, False)] == ("bundle", E["bundle"]["p50"])
      and out[(True, True, False)] == ("bundle_htf", E["bundle_htf"]["p50"]) and out[(True, False, True)] == ("bundle_cfl", E["bundle_cfl"]["p50"])
      and out[(True, True, True)] == ("bundle_htf_cfl", E["bundle_htf_cfl"]["p50"]))   # the numbers from the bot itself
src = open("/home/user/vp-poc-screener/vp_poc_screener.py").read()
ok &= "(e.kind.includes('cfl') ? ' + Классика' : '') + (e.kind.includes('htf') ? ' + HTF' : '')" in src
print("ALL OK" if ok else "FAILED"); sys.exit(0 if ok else 1)
