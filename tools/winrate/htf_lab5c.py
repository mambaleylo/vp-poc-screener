"""the round-5 rules on the 84 check coins (never trained on, not traded by the bot): the same pipeline, R terms"""
src = open("htf_lab5.py").read().split('print("== база')[0]
src = src.replace("base = HTF & (SIDE > 0) & (T >= ts(2023)) & BOT &", "base = HTF & (SIDE > 0) & (T >= ts(2023)) & ~BOT &")
exec(src)
print("контрольные монеты: кандидатов", len(cand0), flush=True)
for nm, kw in (("B0 как в боте", {}), ("K24 стоп по закрытию дня", dict(kh=24)), ("H144 держим 144ч", dict(hold=144)), ("T4H144 тейк 4R 144ч", dict(take=4.0, hold=144)),
               ("P приоритет обеим", dict(prio=True)), ("C20 лимит 20", dict(cap=20)),
               ("E3w48 −0.3 dATR 48ч", dict(depth=0.3, win=48)), ("E5w72 −0.5 dATR 72ч", dict(depth=0.5, win=72)), ("E6w48 −0.6 dATR 48ч", dict(depth=0.6, win=48)),
               ("E6w72 −0.6 dATR 72ч", dict(depth=0.6, win=72)), ("E7w72 −0.7 dATR 72ч", dict(depth=0.7, win=72))):
    run(nm, **kw)
