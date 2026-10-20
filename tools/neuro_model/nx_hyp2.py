import sys, numpy as np
ARGS = sys.argv[1:]
import nx_h as N
q = float(ARGS[0]); F = N.F
def run(nm, mask_fn, **kw):
    ev = []
    for s in (1, -1): ev += N.build(q, mask_fn(s), sides=(s,), **kw)
    N.line(nm, sorted(ev), q)
print(f"== q {q}")
run("сейчас", lambda s: None)
run("ADX<30 + держать 24ч", lambda s: F["adx"] < 30, hold=24)
run("ADX<30 + BTC 1ч < 1% + 24ч", lambda s: (F["adx"] < 30) & (s * F["b_r1"] > -1), hold=24)
run("ADX<25 + 24ч", lambda s: F["adx"] < 25, hold=24)
run("ADX<35 + 24ч", lambda s: F["adx"] < 35, hold=24)
