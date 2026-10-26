"""each lifter alone (SMC 8h/12h longs, Breakout, Cascade) at 1 / 1.5 / 2%: always, only while ⚡ is idle, idle x1 else
x0.3 (quiet4.py's gate d); friction -0.03R"""
exec(open("quiet4.py").read().split("for nm, parts, rk in (")[0])
for nm, p, slot in (("SMC 8h/12h лонги", "smc812L", 0), ("📈 Пробой", "rbx", 1), ("🌊 Каскад", "cas", 2)):
    print("==", nm, flush=True)
    for r in (1.0, 1.5, 2.0):
        rk = [0, 0, 0]; rk[slot] = r
        show(f"{r}% всегда", gated([p], None), rk)
        show(f"{r}% только когда ⚡ простаивает", gated([p], "d"), rk)
        show(f"{r}% ⚡ простаивает ×1, иначе ×0.3", gated([p], "d", 0.3), rk)
