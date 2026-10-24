"""the user: "но ведь когда внедрялась система с запасным стопом ты сказал что так лучше" — the v0.99.692 decision again
with the bot's leverage (sim2: the margin by the emergency stop): the old stop by a touch (no emergency stop: the leverage
by the 2 ATR itself) vs the 1h close + emergency 3 (692), vs the chart's close"""
exec(open("closetf4.py").read().split("r0 = money2(")[0])
def mk3(tk, soft, hard):
    def f(e):
        T, O, H, L, C = h1c(e["sym"])
        return walk5(T, O, H, L, C, e["i1"], e["fbt"] + 32 * e["tfh"] * 3600, e["s"], e["fill"], e["a"], tk, soft, hard, 1, soft)
    return f
r_t = money2("стоп касанием 2 ATR, тейк 1.0 (689)", pool(E, mk3(1.0, 2.0, 2.0)), 2.0)
money2("стоп касанием 2 ATR, тейк 1.1", pool(E, mk2(2.0, 2.0, lambda e: 1)), 2.0)
money2("стоп касанием 2.5 ATR (риск при 2.5)", pool(E, mk2(2.5, 2.5, lambda e: 1, 2.5)), 2.5)
money2("закр. 1ч за 2, авар. 3 (692)", pool(E, mk2(2.0, 3.0, lambda e: 1)), 3.0, ref=r_t)
money2("закр. свечи графика, авар. 3", pool(E, mk2(2.0, 3.0, lambda e: e["tfh"])), 3.0, ref=r_t)
money2("закр. свечи графика, авар. 3.5", pool(E, mk2(2.0, 3.5, lambda e: e["tfh"])), 3.5, ref=r_t)
