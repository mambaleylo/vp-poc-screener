s=open("wickstop.py").read()
head=s.split("@njit\ndef walk")[0]
i=s.index("\nroll = np.arange(ts(2024)"); rest=s[i:]
body=open("partial_walk.txt").read()
rest=rest.replace("def show(nm, soft, hard, close_mode, size_by):","def show(nm, soft, hard, close_mode, size_by, pf=0.0, be=False):")
old='R, k, te = walk(T, O, H, L, C, v["i1"], v["end_t"], v["s"], v["fill"], v["a"], soft, hard, close_mode, size_by, 0.4, 2.0)'
assert old in rest
rest=rest.replace(old,'R, k, te = walk2(T, O, H, L, C, v["i1"], v["end_t"], v["s"], v["fill"], v["a"], soft, hard, close_mode, size_by, 0.4, 2.0, pf, be)')
rest=rest[:rest.index('show("касанием 2 ATR')]
rest+='''show("сейчас (касанием 2 ATR)", 2.0, 2.0, False, 2.0)
for pf in (0.5, 0.33):
    show(f"частичный: {pf:.0%} на +1 ATR, остаток к 2", 2.0, 2.0, False, 2.0, pf)
    show(f"частичный: {pf:.0%} на +1, остаток к 2, стоп в 0", 2.0, 2.0, False, 2.0, pf, True)
show("частичный 50% + закрытие часа 2 / авар. 3, размер от 2", 2.0, 3.0, True, 2.0, 0.5)
show("частичный 50% + закрытие часа 2.5 / авар. 3.5, размер 2.5", 2.5, 3.5, True, 2.5, 0.5)
'''
open("partial.py","w").write(head+body+rest)
