import sys; sys.argv = ["x", "20"]
src = open("money_exact.py").read().split('print("== реальные плечи монет')[0]
src = src.replace('EV.append({"t0": t0 + 3600, "t1": int(t["t_out"]), "r": float(t["r"]), "st": st, "sth": sth, "mod": "dlm", "sym": t["symbol"], "side": t["side"], "e": t["entry"]})',
                  'EV.append({"t0": t0 + 3600, "t1": int(t["t_out"]), "r": float(t["r"]), "st": st, "sth": sth, "mod": "dlm", "sym": t["symbol"], "side": t["side"], "e": t["entry"], "stream": t["st"]})')
src = src.replace('            rd = eq * rk; hn = rd * v["sth"] / v["st"]', '            rk *= WF(v); rd = eq * rk; hn = rd * v["sth"] / v["st"]')
WF = lambda v: 1.0
exec(src)
for nm, f in (("как сейчас", lambda v: 1.0),
              ("2ч-поток x0.7", lambda v: 0.7 if v.get("stream") == "close2h" else 1.0),
              ("шорты ⚡ x0.7", lambda v: 0.7 if v["mod"] == "dlm" and v["side"] < 0 else 1.0),
              ("2ч и шорты x0.7", lambda v: (0.7 if v.get("stream") == "close2h" else 1.0) * (0.7 if v["mod"] == "dlm" and v["side"] < 0 else 1.0)),
              ("4ч-поток x1.3", lambda v: 1.3 if v.get("stream") == "wick4h" else 1.0),
              ("лонги ⚡ x1.3", lambda v: 1.3 if v["mod"] == "dlm" and v["side"] > 0 else 1.0)):
    WF = f
    E, cut, skip, nfree, mdd, mo, mmx, liq, nmx = run(20.0, real=True)
    print(f"{nm:20s} ${E:>10,.0f} | урезано {cut}, пропущено {skip} | просадка {mdd*100:.0f}% | мес: " + " ".join(f"{v:,.0f}" for k, v in sorted(mo.items())), flush=True)
