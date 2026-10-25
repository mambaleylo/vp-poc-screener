"""v0.99.720 — a coin off Binance: the "miss" mark, after it expires asked again (no 'cols' error)"""
import time
from common import V
errs = []; V.log_error = lambda m: errs.append(m)
calls = []
V._bnc_get = lambda bsym, interval, a, b, lim: (calls.append(bsym), False)[1]   # Binance: no such symbol
now = time.time()
r1 = V.bn_closed("EOS_USDT", "2h", 7200, 50, now)
mark = dict(V._BNC.get(("EOS_USDT", "2h")) or {})
r2 = V.bn_closed("EOS_USDT", "2h", 7200, 50, now + 3600)          # within the 6 h: no call
n_mid = len(calls)
r3 = V.bn_closed("EOS_USDT", "2h", 7200, 50, now + 7 * 3600)      # expired: asked again, no error
ok = r1 is None and r2 is None and r3 is None and "miss" in mark and n_mid == 2 and len(calls) == 4 and not errs
print("calls", calls, "errors", errs, "ALL OK" if ok else "FAILED")
