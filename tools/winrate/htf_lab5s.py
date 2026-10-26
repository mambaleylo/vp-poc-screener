"""htf_lab5.py's best ideas and their mixes saved for the money sim (htf_lab5m.py)"""
exec(open("htf_lab5.py").read().split('print("== база')[0])
T4 = dict(take=4.0, hold=144)
for nm, kw in (("B0 как в боте", {}), ("H144 держим 144ч", dict(hold=144)), ("T4H144 тейк 4R 144ч", T4), ("K24 стоп по закрытию дня", dict(kh=24)),
               ("C20 лимит 20", dict(cap=20)), ("P приоритет обеим", dict(prio=True)), ("PC20 приоритет + лимит 20", dict(prio=True, cap=20)),
               ("T4C20 тейк 4R 144ч + лимит 20", dict(cap=20, **T4)), ("T4PC20 тейк 4R 144ч + приоритет + 20", dict(cap=20, prio=True, **T4)),
               ("T4K12PC20 + стоп 12ч", dict(cap=20, prio=True, kh=12, **T4)), ("Q993C20 q0.993 + лимит 20", dict(q=0.993, cap=20)),
               ("E04 лимит −0.4 dATR 48ч", dict(depth=0.4, win=48)), ("E06 лимит −0.6 dATR 48ч", dict(depth=0.6, win=48)),
               ("E04C20 лимит −0.4 + лимит 20", dict(depth=0.4, win=48, cap=20))):
    run(nm, save=True, **kw)
