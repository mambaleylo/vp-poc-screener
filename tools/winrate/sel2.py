s = open("sel.py").read().split("for nm, f in (")[0]
exec(s)
for nm, f in (("как сейчас", lambda v: 1.0),
              ("2ч-шорты x0.7", lambda v: 0.7 if v.get("stream") == "close2h" and v["side"] < 0 else 1.0),
              ("2ч-шорты x0.5", lambda v: 0.5 if v.get("stream") == "close2h" and v["side"] < 0 else 1.0),
              ("2ч-шорты не брать", lambda v: 0.0001 if v.get("stream") == "close2h" and v["side"] < 0 else 1.0)):
    WF = f
    E, cut, skip, nfree, mdd, mo, mmx, liq, nmx = run(20.0, real=True)
    print(f"{nm:18s} ${E:>10,.0f} | урезано {cut}, пропущено {skip} | просадка {mdd*100:.0f}% | мес: " + " ".join(f"{v:,.0f}" for k, v in sorted(mo.items())), flush=True)
