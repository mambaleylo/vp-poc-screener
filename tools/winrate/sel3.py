s = open("sel.py").read().split("for nm, f in (")[0]
exec(s)
import calendar
STARTS = [calendar.timegm((2026, m, d, 0, 0, 0)) for m in (1, 2, 3, 4, 5, 6) for d in (1, 15)]
VARS = (("как сейчас", lambda v: 1.0),
        ("2ч-шорты x0.7", lambda v: 0.7 if v.get("stream") == "close2h" and v["side"] < 0 else 1.0),
        ("2ч-шорты x0.5", lambda v: 0.5 if v.get("stream") == "close2h" and v["side"] < 0 else 1.0),
        ("2ч и все шорты x0.7", lambda v: (0.7 if v.get("stream") == "close2h" else 1.0) * (0.7 if v["mod"] == "dlm" and v["side"] < 0 else 1.0)))
res = {}
for nm, f in VARS:
    WF = f; out = []
    for st0 in STARTS:
        A = st0
        E, cut, skip, nfree, mdd, mo, mmx, liq, nmx = run(20.0, real=True)
        out.append((E, mdd))
    res[nm] = out
base = res["как сейчас"]
for nm, out in res.items():
    q = [o[0] / b[0] for o, b in zip(out, base)]
    print(f"{nm:20s} лучше в {sum(x > 1 for x in q)} из {len(q)} стартов | отношение к текущему: медиана x{sorted(q)[len(q)//2]:.2f}, худшее x{min(q):.2f}, лучшее x{max(q):.2f} | просадка медиана {sorted(o[1] for o in out)[len(out)//2]*100:.0f}%", flush=True)
