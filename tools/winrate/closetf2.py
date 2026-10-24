"""closetf693 follow-up: the stop on a longer candle's close won (4h: the median $6 933 vs $5 459). Robustness: kh 1..12,
the chart's own candle (4h stream 4h, 2h stream 2h), by window (how often beats 1h), by stream, risk"""
exec(open("closetf693.py").read().split("P0 = pool(")[0])
def wins(P, rk=0.04):
    A = np.array([p[:5] for p in P], float); t0, t1, R, STv, K = A.T
    return np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, rk, -0.025)[0] for s_ in roll])
def mk2(soft, hard, kfun, size_by=2.0):
    def f(e):
        T, O, H, L, C = h1c(e["sym"])
        return walk5(T, O, H, L, C, e["i1"], e["fbt"] + 32 * e["tfh"] * 3600, e["s"], e["fill"], e["a"], 1.1, soft, hard, kfun(e), size_by)
    return f
P1 = pool(E, mk2(2.0, 3.0, lambda e: 1)); w1 = wins(P1)
for nm, kf in [("закр. 2ч", lambda e: 2), ("закр. 3ч", lambda e: 3), ("закр. 4ч", lambda e: 4), ("закр. 6ч", lambda e: 6), ("закр. 8ч", lambda e: 8), ("закр. 12ч", lambda e: 12),
               ("закр. свечи графика (4ч/2ч)", lambda e: e["tfh"])]:
    P = pool(E, mk2(2.0, 3.0, kf)); money(nm + " за 2, авар. 3", P); w = wins(P)
    print(f"   окон лучше чем 1ч: {np.mean(w > w1)*100:.0f}% · отношение медиан окон {np.median(w / w1):.2f}", flush=True)
print("== закр. 4ч: аварийный стоп / риск")
money("закр. 4ч за 2, авар. 3.5 (риск при 2)", pool(E, mk2(2.0, 3.5, lambda e: 4)))
money("закр. 4ч за 2, авар. 2.75", pool(E, mk2(2.0, 2.75, lambda e: 4)))
P4 = pool(E, mk2(2.0, 3.0, lambda e: 4))
for r in (0.03, 0.05): money(f"закр. 4ч, риск {r*100:.0f}%", P4, rk=r)
print("== по потокам (только этот поток)")
for tfh in (4, 2):
    Es = [e for e in E if e["tfh"] == tfh]
    money(f"поток {tfh}ч: закр. 1ч", pool(Es, mk2(2.0, 3.0, lambda e: 1)))
    money(f"поток {tfh}ч: закр. 4ч", pool(Es, mk2(2.0, 3.0, lambda e: 4)))
