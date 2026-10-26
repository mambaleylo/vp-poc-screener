"""📏 HTF win rate: the deployed pipeline (htf_lab5.py) + the soft stop's distance (sk x dATR below the level, the hard
stays 3 dATR), a nearer take, a partial at +1R, the close-stop on 1d, break-even / trailing; the selection: both models
at a relaxed q (alone, or OR the deployed rule). argv: [chk]"""
import sys
CHK = "chk" in sys.argv
src = open("htf_lab5.py").read().split('print("== база')[0]
src = src.replace("def walk(O, H, L, C, Tb, j, lv, datr, depth, win, hard_a, take, hold, kh, be_at, tr_at, tr_d, pf, pr, sfill=False):", "def walk(O, H, L, C, Tb, j, lv, datr, depth, win, hard_a, take, hold, kh, be_at, tr_at, tr_d, pf, pr, sfill, sk):")
src = src.replace("ssl = (fill - r0) if sfill else (lv - r0);", "ssl = (fill - sk * r0) if sfill else (lv - sk * r0);")
src = src.replace("filt=None, cap=12, save=False, prio=False, sfill=False):", "filt=None, cap=12, save=False, prio=False, sfill=False, sk=1.0, both=None):")
src = src.replace("hold, kh, be_at, tr_at, tr_d, pf, pr, sfill)\n", "hold, kh, be_at, tr_at, tr_d, pf, pr, sfill, sk)\n")
src = src.replace("""    m = (Po[cand0] >= q) | (Pn[cand0] >= q)
    c = cand0[m]""", """    m = (Po[cand0] >= q) | (Pn[cand0] >= q)
    if both is not None: m = ((Po[cand0] >= both[0]) & (Pn[cand0] >= both[0])) | (m if both[1] else False)
    c = cand0[m]""")
src = src.replace("cand0 = np.where(base & ((Po >= 0.99) | (Pn >= 0.99)))[0]", "cand0 = np.where(base & ((Po >= 0.97) | (Pn >= 0.97)))[0]")
if CHK: src = src.replace("base = HTF & (SIDE > 0) & (T >= ts(2023)) & BOT &", "base = HTF & (SIDE > 0) & (T >= ts(2023)) & ~BOT &")
assert "sk * r0" in src and "both[0]" in src and "pr, sfill, sk)" in src and "both=None):" in src
exec(src)
print("== монеты", "контрольные" if CHK else "бота", flush=True)
V = [("B0 как в боте", {}),
     ("T1 тейк 1R", dict(take=1.0)), ("T15 тейк 1.5R", dict(take=1.5)), ("T2 тейк 2R", dict(take=2.0)),
     ("S15 стоп 1.5 dATR", dict(sk=1.5)), ("S2 стоп 2 dATR", dict(sk=2.0)),
     ("S15T2 стоп 1.5, тейк 2R", dict(sk=1.5, take=2.0)), ("S15T15 стоп 1.5, тейк 1.5R", dict(sk=1.5, take=1.5)),
     ("S2T15 стоп 2, тейк 1.5R", dict(sk=2.0, take=1.5)),
     ("K24 стоп по закрытию дня", dict(kh=24)), ("K24T2 + тейк 2R", dict(kh=24, take=2.0)), ("K24S15 + стоп 1.5", dict(kh=24, sk=1.5)),
     ("P1 половина на +1R", dict(pf=0.5, pr=1.0)), ("P1K24 + стоп по дню", dict(pf=0.5, pr=1.0, kh=24)),
     ("TR трейл после +1.5R", dict(tr_at=1.5, tr_d=1.0)),
     ("BOTH99 обе модели ≥q0.99", dict(both=(0.99, False))), ("BOTH98 обе ≥q0.98", dict(both=(0.98, False))), ("BOTH97 обе ≥q0.97", dict(both=(0.97, False))),
     ("BOTH98K24 обе ≥0.98 + стоп по дню", dict(both=(0.98, False), kh=24)), ("BOTH98S15 обе ≥0.98 + стоп 1.5", dict(both=(0.98, False), sk=1.5)),
     ("BOTH98T2 обе ≥0.98 + тейк 2R", dict(both=(0.98, False), take=2.0))]
for nm, kw in V:
    run(nm, save=not CHK, **kw)
