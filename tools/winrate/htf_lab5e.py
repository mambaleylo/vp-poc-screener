"""the deeper limit (htf_lab5.py E*): robustness — depth 0.3..0.8 dATR, waiting 24/48/72 h, the stop at the level (lv - 1)
or under the fill (fill - 1, the hard fill - 3); lists saved for the money"""
exec(open("htf_lab5.py").read().split('print("== база')[0])
for sf in (False, True):
    print("== стоп", "от входа (вход − 1 dATR, аварийный −3)" if sf else "от уровня (уровень − 1 dATR, аварийный −3)", flush=True)
    for d in (0.3, 0.5, 0.6, 0.7, 0.8):
        for w in (24, 48, 72):
            run(f"E{'f' if sf else ''}{int(d * 10)}w{w} −{d} dATR {w}ч", depth=d, win=w, sfill=sf, save=True)
