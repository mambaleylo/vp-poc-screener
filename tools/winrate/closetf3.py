"""closetf2 follow-up: the stop on the close of the chart's own candle (4h stream 4h, 2h stream 2h) — the emergency stop
level, by stream, windows vs the 1h close"""
exec(open("closetf2.py").read().split("P1 = pool(")[0])
P1 = pool(E, mk2(2.0, 3.0, lambda e: 1)); w1 = wins(P1)
for hard in (3.0, 3.25, 3.5, 4.0):
    P = pool(E, mk2(2.0, hard, lambda e: e["tfh"])); money(f"закр. свечи графика, авар. {hard}", P); w = wins(P)
    print(f"   окон лучше чем 1ч: {np.mean(w > w1)*100:.0f}% · отношение медиан окон {np.median(w / w1):.2f}", flush=True)
for tfh in (4, 2):
    Es = [e for e in E if e["tfh"] == tfh]
    money(f"поток {tfh}ч: закр. {tfh}ч, авар. 3", pool(Es, mk2(2.0, 3.0, lambda e: e["tfh"])))
    money(f"поток {tfh}ч: закр. {tfh}ч, авар. 3.5", pool(Es, mk2(2.0, 3.5, lambda e: e["tfh"])))
