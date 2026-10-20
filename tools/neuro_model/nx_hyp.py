import sys, numpy as np
ARGS = sys.argv[1:]
import nx_h as N
q = float(ARGS[0]); part = ARGS[1]
F = N.F
def run(nm, mask=None, sides=(1, -1), sgn_mask=None, **kw):
    if sgn_mask is not None:
        tr = []
        ev = []
        for s in sides:
            m = sgn_mask(s) if mask is None else (sgn_mask(s) & mask)
            ev += N.build(q, m, sides=(s,), **kw)
        # re-replay jointly for the side caps is per side anyway; one side at a time is exact
        tr = sorted(ev)
    else:
        tr = N.build(q, mask, sides=sides, **kw)
    N.line(nm, tr, q)
print(f"== q {q}")
if part == "base":
    run("сейчас: стоп 1 ATR, тейк 3R, 48ч")
    run("только лонги", sides=(1,)); run("только шорты", sides=(-1,))
    for lim in (4, 2):
        run(f"BTC за 24ч против сделки < {lim}%", sgn_mask=lambda s, l=lim: s * F["b_r24"] > -l)
    run("BTC за 1ч против сделки < 1%", sgn_mask=lambda s: s * F["b_r1"] > -1)
    run("BTC с той стороны EMA50 (по сделке)", sgn_mask=lambda s: s * F["b_e50"] > 0)
    run("монета по тренду дня (EMA200)", sgn_mask=lambda s: s * F["dd_e200"] > 0)
    run("ADX < 30", F["adx"] < 30)
if part == "exits":
    run("сейчас")
    for a in (1.5, 2.0): run(f"стоп {a} ATR", stop_k=a)
    for tk in (2.0, 4.0, 6.0): run(f"тейк {tk}R", take=tk)
    for h in (24, 96): run(f"держать {h}ч", hold=h)
    for cs, hd in ((1.0, 2.0), (1.5, 3.0)): run(f"стоп {cs} по закрытию, авар. {hd}", close_soft=cs, hard=hd)
